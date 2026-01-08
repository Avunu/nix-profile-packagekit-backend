#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Licensed under the GNU General Public License Version 2
#
# Nix Profile management for PackageKit backend

"""
Module for parsing and managing the user's nix profile.

This module handles:
- Parsing ~/.nix-profile/manifest.json
- Extracting installed package information
- Mapping store paths to package names
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class NixProfile:
    """
    Manager for the user's nix profile.
    Parses manifest.json and provides package information.
    """
    
    def __init__(self, profile_path: Optional[str] = None):
        """
        Initialize the nix profile manager.
        
        Args:
            profile_path: Path to profile directory. Defaults to ~/.nix-profile
        """
        if profile_path is None:
            home = os.environ.get('HOME')
            if not home:
                raise ValueError("HOME environment variable not set")
            profile_path = os.path.join(home, '.nix-profile')
        
        self.profile_path = Path(profile_path)
        self.manifest_path = self.profile_path / 'manifest.json'
    
    def get_installed_packages(self) -> Dict[str, str]:
        """
        Get all installed packages with their versions.
        
        Returns:
            Dictionary mapping package attribute names to versions.
            Example: {'firefox': '122.0', 'vim': '9.0.1'}
        """
        if not self.manifest_path.exists():
            return {}
        
        try:
            with open(self.manifest_path, 'r') as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to parse manifest.json: {e}")
            return {}
        
        packages = {}
        elements = manifest.get('elements', [])
        
        for element in elements:
            # Extract package name from attrPath
            attr_path = element.get('attrPath')
            if not attr_path:
                # Try to extract from originalUrl or storePaths
                original_url = element.get('originalUrl', '')
                if original_url:
                    attr_path = self._extract_name_from_url(original_url)
                else:
                    continue
            
            # Extract version from store paths
            store_paths = element.get('storePaths', [])
            version = 'unknown'
            
            if store_paths:
                # Store paths look like: /nix/store/hash-name-version
                # Parse the first store path
                store_path = store_paths[0]
                version = self._extract_version_from_store_path(store_path, attr_path)
            
            packages[attr_path] = version
        
        return packages
    
    def find_package_index(self, package_name: str) -> Optional[int]:
        """
        Find the profile element index for a package.
        
        Args:
            package_name: Package attribute name
            
        Returns:
            Element index (for use with nix profile remove/upgrade) or None
        """
        if not self.manifest_path.exists():
            return None
        
        try:
            with open(self.manifest_path, 'r') as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
        
        elements = manifest.get('elements', [])
        
        for i, element in enumerate(elements):
            attr_path = element.get('attrPath')
            if attr_path == package_name:
                return i
            
            # Also check originalUrl
            original_url = element.get('originalUrl', '')
            if package_name in original_url:
                return i
        
        return None
    
    def get_package_info(self, package_name: str) -> Optional[Dict]:
        """
        Get detailed information about an installed package.
        
        Args:
            package_name: Package attribute name
            
        Returns:
            Dictionary with package information or None
        """
        if not self.manifest_path.exists():
            return None
        
        try:
            with open(self.manifest_path, 'r') as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
        
        elements = manifest.get('elements', [])
        
        for element in elements:
            attr_path = element.get('attrPath')
            if attr_path == package_name:
                return {
                    'attrPath': attr_path,
                    'originalUrl': element.get('originalUrl', ''),
                    'storePaths': element.get('storePaths', []),
                    'url': element.get('url', ''),
                }
        
        return None
    
    def _extract_name_from_url(self, url: str) -> str:
        """
        Extract package name from a flake URL.
        
        Examples:
            nixpkgs#firefox -> firefox
            github:NixOS/nixpkgs#vim -> vim
        """
        if '#' in url:
            return url.split('#')[-1]
        return url.split('/')[-1]
    
    def _extract_version_from_store_path(self, store_path: str, package_name: str) -> str:
        """
        Extract version from a nix store path.
        
        Store paths look like: /nix/store/abc123...-package-name-version
        
        Args:
            store_path: Full store path
            package_name: Package name to help identify version
            
        Returns:
            Version string or 'unknown'
        """
        try:
            # Get the last component of the path
            basename = Path(store_path).name
            
            # Remove hash prefix (everything before first -)
            if '-' not in basename:
                return 'unknown'
            
            parts = basename.split('-', 1)
            if len(parts) < 2:
                return 'unknown'
            
            name_version = parts[1]
            
            # Try to separate name from version
            # Common patterns:
            # - firefox-122.0
            # - python3.11-numpy-1.24.3
            # - vim-9.0.1
            
            # If package_name is in the string, try to extract what comes after
            if package_name in name_version:
                # Find the package name and get the rest
                idx = name_version.find(package_name)
                if idx != -1:
                    remainder = name_version[idx + len(package_name):]
                    # Remove leading dash if present
                    if remainder.startswith('-'):
                        remainder = remainder[1:]
                    
                    # The version is usually the first component
                    if remainder:
                        # Split on dash and take first part as version
                        version = remainder.split('-')[0]
                        if version:
                            return version
            
            # Fallback: try to find version-like patterns (numbers and dots)
            parts = name_version.split('-')
            for part in reversed(parts):
                # Check if this part looks like a version
                if any(c.isdigit() for c in part) and ('.' in part or part[0].isdigit()):
                    return part
            
            return 'unknown'
            
        except Exception:
            return 'unknown'
    
    def is_empty(self) -> bool:
        """Check if the profile is empty or doesn't exist."""
        if not self.manifest_path.exists():
            return True
        
        try:
            with open(self.manifest_path, 'r') as f:
                manifest = json.load(f)
            elements = manifest.get('elements', [])
            return len(elements) == 0
        except (json.JSONDecodeError, IOError):
            return True
