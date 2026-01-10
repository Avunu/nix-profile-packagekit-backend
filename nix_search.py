#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Licensed under the GNU General Public License Version 2
#
# Nix search integration for PackageKit backend

"""
Module for searching nixpkgs packages using native nix commands.

Uses `nix search` at runtime - always up-to-date with the current flake registry.
No external databases or build-time dependencies required.
"""

import json
import subprocess
from typing import Dict, List, Optional, Tuple


class NixSearch:
    """
    Search nixpkgs using native `nix search` command.
    
    This approach:
    - Always uses current nixpkgs from flake registry
    - No build-time data dependencies
    - No cache staleness issues
    """
    
    def __init__(self, flake_ref: str = "nixpkgs"):
        """
        Initialize the nix search wrapper.
        
        Args:
            flake_ref: Flake reference to search (default: "nixpkgs" from registry)
        """
        self.flake_ref = flake_ref
        self._cache: Dict[str, Dict] = {}
    
    def search(self, terms: List[str], limit: int = 100) -> Dict[str, Dict]:
        """
        Search for packages by name/description.
        
        Args:
            terms: Search terms
            limit: Maximum results to return
            
        Returns:
            Dictionary mapping package attribute paths to metadata
        """
        results = {}
        
        for term in terms:
            try:
                # Run nix search with JSON output
                result = subprocess.run(
                    ['nix', 'search', self.flake_ref, term, '--json'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode != 0:
                    print(f"nix search failed: {result.stderr}")
                    continue
                
                if not result.stdout.strip():
                    continue
                
                packages = json.loads(result.stdout)
                
                for attr_path, info in packages.items():
                    # attr_path is like "legacyPackages.x86_64-linux.firefox"
                    # Extract just the package name
                    parts = attr_path.split('.')
                    pkg_name = parts[-1] if parts else attr_path
                    
                    results[pkg_name] = {
                        'pname': info.get('pname', pkg_name),
                        'version': info.get('version', 'unknown'),
                        'description': info.get('description', ''),
                        'summary': (info.get('description', '')[:200] 
                                   if info.get('description') else ''),
                    }
                    
                    if len(results) >= limit:
                        break
                        
            except subprocess.TimeoutExpired:
                print(f"nix search timed out for term: {term}")
            except json.JSONDecodeError as e:
                print(f"Failed to parse nix search output: {e}")
            except Exception as e:
                print(f"Error during nix search: {e}")
        
        return results
    
    def get_package_info(self, package_name: str) -> Optional[Dict]:
        """
        Get detailed info for a specific package.
        
        Args:
            package_name: Package attribute name
            
        Returns:
            Package metadata or None
        """
        # Check cache first
        if package_name in self._cache:
            return self._cache[package_name]
        
        try:
            # Use nix eval to get package metadata
            result = subprocess.run(
                ['nix', 'eval', f'{self.flake_ref}#{package_name}.meta', '--json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                # Try without .meta (some packages might not have it)
                return self._get_basic_info(package_name)
            
            meta = json.loads(result.stdout)
            
            # Get version separately
            version_result = subprocess.run(
                ['nix', 'eval', f'{self.flake_ref}#{package_name}.version', '--raw'],
                capture_output=True,
                text=True,
                timeout=10
            )
            version = version_result.stdout if version_result.returncode == 0 else 'unknown'
            
            info = {
                'pname': package_name,
                'version': version,
                'description': meta.get('description', ''),
                'summary': (meta.get('description', '')[:200] 
                           if meta.get('description') else ''),
                'homepage': meta.get('homepage', ''),
                'license': self._format_license(meta.get('license')),
                'maintainers': self._format_maintainers(meta.get('maintainers', [])),
            }
            
            self._cache[package_name] = info
            return info
            
        except subprocess.TimeoutExpired:
            print(f"nix eval timed out for: {package_name}")
        except json.JSONDecodeError as e:
            print(f"Failed to parse nix eval output: {e}")
        except Exception as e:
            print(f"Error getting package info: {e}")
        
        return None
    
    def _get_basic_info(self, package_name: str) -> Optional[Dict]:
        """Get basic info when full metadata isn't available."""
        try:
            # Just get version
            result = subprocess.run(
                ['nix', 'eval', f'{self.flake_ref}#{package_name}.version', '--raw'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return {
                    'pname': package_name,
                    'version': result.stdout,
                    'description': '',
                    'summary': '',
                }
        except Exception:
            pass
        
        return None
    
    def _format_license(self, license_info) -> str:
        """Format license information from nix meta."""
        if not license_info:
            return 'unknown'
        
        if isinstance(license_info, str):
            return license_info
        
        if isinstance(license_info, dict):
            return license_info.get('spdxId', license_info.get('shortName', 'unknown'))
        
        if isinstance(license_info, list):
            # Multiple licenses
            names = []
            for lic in license_info:
                if isinstance(lic, dict):
                    names.append(lic.get('spdxId', lic.get('shortName', '')))
                elif isinstance(lic, str):
                    names.append(lic)
            return ' AND '.join(filter(None, names)) or 'unknown'
        
        return 'unknown'
    
    def _format_maintainers(self, maintainers: List) -> List[str]:
        """Format maintainer information."""
        result = []
        for m in maintainers:
            if isinstance(m, dict):
                name = m.get('name', m.get('github', ''))
                if name:
                    result.append(name)
            elif isinstance(m, str):
                result.append(m)
        return result
    
    def resolve_package(self, package_name: str) -> Optional[Tuple[str, str]]:
        """
        Resolve a package name to its attribute path and version.
        
        Args:
            package_name: Package name to resolve
            
        Returns:
            Tuple of (attribute_path, version) or None
        """
        info = self.get_package_info(package_name)
        if info:
            return (package_name, info.get('version', 'unknown'))
        
        # Try searching for it
        results = self.search([package_name], limit=5)
        if package_name in results:
            return (package_name, results[package_name].get('version', 'unknown'))
        
        # Check if any result is an exact match
        for name, info in results.items():
            if info.get('pname') == package_name:
                return (name, info.get('version', 'unknown'))
        
        return None
