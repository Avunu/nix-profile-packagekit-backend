#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Licensed under the GNU General Public License Version 2
#
# Nixpkgs appdata integration for PackageKit backend

"""
Module for managing nixpkgs package data.

This module integrates with snowfallorg data repositories:
- nix-data-db: Pre-built SQLite databases with package metadata
- nixos-appstream-data: AppStream XML files for detailed app information

Provides:
- Downloading pre-built databases from nix-data-db
- Caching databases locally
- Searching package metadata
- Providing descriptions and other metadata
"""

import json
import os
import sqlite3
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set

# Import AppStream parser for rich metadata
try:
    from appstream_parser import AppStreamParser
    APPSTREAM_AVAILABLE = True
except ImportError:
    APPSTREAM_AVAILABLE = False
    print("Warning: AppStream parser not available")


class NixpkgsAppdata:
    """
    Manager for nixpkgs appdata streams.
    Downloads pre-built databases from snowfallorg/nix-data-db.
    """
    
    # GitHub repositories for data
    DATA_DB_REPO = "https://github.com/snowfallorg/nix-data-db"
    APPSTREAM_REPO = "https://github.com/snowfallorg/nixos-appstream-data"
    
    # Raw content URLs for direct download
    DATA_DB_RAW = "https://raw.githubusercontent.com/snowfallorg/nix-data-db/main"
    APPSTREAM_RAW = "https://raw.githubusercontent.com/snowfallorg/nixos-appstream-data/main"
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the appdata manager.
        
        Args:
            cache_dir: Directory for caching appdata. Defaults to ~/.cache/packagekit-nix
        """
        if cache_dir is None:
            home = os.environ.get('HOME')
            if not home:
                raise ValueError("HOME environment variable not set")
            cache_dir = os.path.join(home, '.cache', 'packagekit-nix')
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Detect which channel to use (default: nixos-unstable)
        self.channel = self._detect_channel()
        
        self.db_file = self.cache_dir / f'{self.channel}_nixpkgs.db'
        self.db_compressed = self.cache_dir / f'{self.channel}_nixpkgs.db.br'
        self.version_file = self.cache_dir / f'{self.channel}_nixpkgs.ver'
        
        # Initialize AppStream parser for rich metadata
        if APPSTREAM_AVAILABLE:
            try:
                self.appstream = AppStreamParser()
                print(f"AppStream parser initialized: {self.appstream.appstream_dir}")
            except Exception as e:
                print(f"Warning: Could not initialize AppStream parser: {e}")
                self.appstream = None
        else:
            self.appstream = None
        
        # In-memory cache
        self._metadata_cache: Optional[Dict] = None
    
    def _detect_channel(self) -> str:
        """
        Detect which NixOS/nixpkgs channel to use.
        Returns channel name like 'nixos-unstable', 'nixos-23.05', etc.
        """
        import subprocess
        
        # Try to detect from nixos-version
        try:
            result = subprocess.run(
                ['nixos-version'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                # Extract version like "23.05" from output
                if 'pre' in version or 'unstable' in version:
                    return 'nixos-unstable'
                else:
                    # Extract X.Y version
                    parts = version.split('.')
                    if len(parts) >= 2:
                        return f'nixos-{parts[0]}.{parts[1]}'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check nix registry for nixpkgs
        try:
            result = subprocess.run(
                ['nix', 'registry', 'list'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'nixpkgs' in line.lower():
                        if 'unstable' in line:
                            return 'nixpkgs-unstable'
                        # Try to extract version
                        import re
                        match = re.search(r'(\d+)\.(\d+)', line)
                        if match:
                            return f'nixos-{match.group(1)}.{match.group(2)}'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Default to nixpkgs-unstable
        return 'nixpkgs-unstable'
    
    def refresh_cache(self, force: bool = False):
        """
        Download and update the appdata cache from nix-data-db.
        
        Args:
            force: Force re-download even if cache exists
        """
        # Check if we need to download
        if not force and self.db_file.exists():
            # Check if file is recent (less than 24 hours old)
            import time
            file_age = time.time() - self.db_file.stat().st_mtime
            if file_age < 86400:  # 24 hours
                print("Database cache is recent, skipping download")
                return
        
        print(f"Downloading nixpkgs database for {self.channel}...")
        
        try:
            # Download the .db.br file
            db_url = f"{self.DATA_DB_RAW}/{self.channel}/nixpkgs.db.br"
            print(f"Downloading from: {db_url}")
            
            urllib.request.urlretrieve(db_url, self.db_compressed)
            print(f"Downloaded compressed database to {self.db_compressed}")
            
            # Decompress with brotli
            self._decompress_database()
            
            # Download version file
            try:
                ver_url = f"{self.DATA_DB_RAW}/{self.channel}/nixpkgs.ver"
                urllib.request.urlretrieve(ver_url, self.version_file)
            except Exception as e:
                print(f"Warning: Could not download version file: {e}")
            
            # Clear the metadata cache to force reload
            self._metadata_cache = None
            
            print(f"Database ready at {self.db_file}")
            
        except Exception as e:
            print(f"Warning: Failed to download database: {e}")
            # If we have cached data, continue using it
            if not self.db_file.exists():
                raise
    
    def _decompress_database(self):
        """Decompress the brotli-compressed database."""
        try:
            import brotli
        except ImportError:
            # Try using brotli command line tool
            import subprocess
            try:
                subprocess.run(
                    ['brotli', '-d', '-o', str(self.db_file), str(self.db_compressed)],
                    check=True
                )
                print(f"Decompressed database with brotli tool")
                return
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                raise ImportError(
                    "brotli is required for decompression. "
                    "Install with: pip install brotli or nix-shell -p python3Packages.brotli"
                ) from e
        
        # Use Python brotli library
        with open(self.db_compressed, 'rb') as f_in:
            compressed_data = f_in.read()
        
        decompressed_data = brotli.decompress(compressed_data)
        
        with open(self.db_file, 'wb') as f_out:
            f_out.write(decompressed_data)
        
        print(f"Decompressed database with Python brotli")
    
    def get_package_metadata(self, package_name: str) -> Optional[Dict]:
        """
        Get metadata for a specific package from the nix-data-db database.
        
        Args:
            package_name: Package attribute name
            
        Returns:
            Dictionary with package metadata or None
        """
        # Ensure we have cached data
        if not self.db_file.exists():
            try:
                self.refresh_cache()
            except Exception:
                return None
        
        if not self.db_file.exists():
            return None
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # The nix-data-db schema uses 'attribute' and 'pname' columns
            cursor.execute('''
                SELECT pname, version, description, homepage, license
                FROM packages WHERE attribute = ? OR pname = ?
            ''', (package_name, package_name))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                metadata = {
                    'pname': row[0] or package_name,
                    'version': row[1] or 'unknown',
                    'summary': row[2][:200] if row[2] else '',  # First 200 chars as summary
                    'description': row[2] or '',
                    'homepage': row[3] or '',
                    'license': row[4] or 'unknown',
                    'categories': [],
                    'icon': '',
                    'screenshots': [],
                }
                
                # Enhance with AppStream data if available
                if self.appstream:
                    appstream_data = self.appstream.get_package_appstream(package_name)
                    if appstream_data:
                        metadata['categories'] = appstream_data.get('categories', [])
                        metadata['icon'] = self._get_best_icon(appstream_data.get('icons', []))
                        metadata['screenshots'] = appstream_data.get('screenshots', [])
                        # Use AppStream summary if available and more detailed
                        if appstream_data.get('summary'):
                            metadata['summary'] = appstream_data['summary']
                        # Prefer AppStream description if available
                        if appstream_data.get('description'):
                            metadata['description'] = appstream_data['description']
                
                return metadata
            
            return None
            
        except Exception as e:
            print(f"Error querying database: {e}")
            return None
    
    def _get_best_icon(self, icons: List[Dict]) -> str:
        """Extract the best icon name from AppStream icons list."""
        if not icons:
            return ''
        
        # Prefer cached icons over stock
        cached = [i for i in icons if i.get('type') == 'cached']
        if cached:
            return cached[0].get('name', '')
        
        # Fall back to stock icon
        stock = [i for i in icons if i.get('type') == 'stock']
        if stock:
            return stock[0].get('name', '')
        
        # Return first icon
        return icons[0].get('name', '')
    
    def search_packages(self, search_terms: List[str], search_descriptions: bool = False) -> Dict[str, Dict]:
        """
        Search for packages by name and optionally description.
        
        Args:
            search_terms: List of search terms (lowercase)
            search_descriptions: Whether to search in descriptions
            
        Returns:
            Dictionary mapping package names to their metadata
        """
        if not self.db_file.exists():
            return {}
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            results = {}
            
            for term in search_terms:
                if search_descriptions:
                    # Search in both attribute name and description
                    cursor.execute('''
                        SELECT attribute, pname, version, description, homepage, license
                        FROM packages
                        WHERE attribute LIKE ? OR pname LIKE ? OR description LIKE ?
                        LIMIT 100
                    ''', (f'%{term}%', f'%{term}%', f'%{term}%'))
                else:
                    # Simple name search
                    cursor.execute('''
                        SELECT attribute, pname, version, description, homepage, license
                        FROM packages
                        WHERE attribute LIKE ? OR pname LIKE ?
                        LIMIT 100
                    ''', (f'%{term}%', f'%{term}%'))
                
                for row in cursor.fetchall():
                    pkg_key = row[0] or row[1]  # attribute or pname
                    results[pkg_key] = {
                        'pname': row[1] or pkg_key,
                        'version': row[2] or 'unknown',
                        'summary': row[3][:200] if row[3] else '',
                        'description': row[3] or '',
                        'homepage': row[4] or '',
                        'license': row[5] or 'unknown',
                        'categories': [],
                        'icon': '',
                    }
            
            conn.close()
            return results
            
        except Exception as e:
            print(f"Error searching database: {e}")
            return {}
    
    def search_by_category(self, categories: List[str]) -> Dict[str, Dict]:
        """
        Search for packages by category using AppStream data.
        
        Args:
            categories: List of categories to search for
            
        Returns:
            Dictionary mapping package names to their metadata
        """
        if not self.appstream:
            print("Warning: AppStream parser not available for category search")
            return {}
        
        # Get package names matching categories
        matching_pkgs = self.appstream.search_by_category(categories)
        
        if not matching_pkgs:
            return {}
        
        # Fetch full metadata for matching packages
        results = {}
        for pkg_name in matching_pkgs:
            metadata = self.get_package_metadata(pkg_name)
            if metadata:
                results[pkg_name] = metadata
        
        return results
