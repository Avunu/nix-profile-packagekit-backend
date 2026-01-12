#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Licensed under the GNU General Public License Version 2
#
# Nix search integration for PackageKit backend using nix-search-cli

"""
Module for searching nixpkgs packages using nix-search-cli.

Uses search.nixos.org ElasticSearch index via nix-search-cli for instant results.
https://github.com/peterldowns/nix-search-cli
"""

import json
import subprocess
from typing import Dict, List, Optional, Tuple


class NixSearch:
    """
    Search nixpkgs using nix-search-cli (queries search.nixos.org).
    
    This is much faster than `nix search` because it uses a pre-built
    ElasticSearch index rather than evaluating nixpkgs.
    
    Requires nix-search-cli to be installed (bundled via flake.nix).
    """
    
    def __init__(self, channel: str = "unstable"):
        """
        Initialize the nix search wrapper.
        
        Args:
            channel: Channel to search (default: "unstable")
        """
        self.channel = channel
        self._cache: Dict[str, Dict] = {}
    
    def search(self, terms: List[str], limit: int = 100) -> Dict[str, Dict]:
        """
        Search for packages by name/description.
        
        Args:
            terms: Search terms
            limit: Maximum results to return
            
        Returns:
            Dictionary mapping package attribute names to metadata
        """
        results = {}
        search_query = ' '.join(terms)
        
        try:
            cmd = [
                'nix-search',
                '--search', search_query,
                '--channel', self.channel,
                '--max-results', str(limit),
                '--json'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"nix-search failed: {result.stderr}")
                return {}
            
            # Parse JSON lines output
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    pkg = json.loads(line)
                    attr_name = pkg.get('package_attr_name', '')
                    if not attr_name:
                        continue
                    
                    results[attr_name] = self._parse_package(pkg)
                    
                except json.JSONDecodeError:
                    continue
                    
        except subprocess.TimeoutExpired:
            print(f"nix-search timed out")
        except Exception as e:
            print(f"Error during nix-search: {e}")
        
        return results
    
    def search_by_name(self, name: str, limit: int = 20) -> Dict[str, Dict]:
        """Search by package attribute name."""
        results = {}
        
        try:
            cmd = [
                'nix-search',
                '--name', name,
                '--channel', self.channel,
                '--max-results', str(limit),
                '--json'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {}
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    pkg = json.loads(line)
                    attr_name = pkg.get('package_attr_name', '')
                    if attr_name:
                        results[attr_name] = self._parse_package(pkg)
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"Error during nix-search: {e}")
        
        return results
    
    def search_by_program(self, program: str, limit: int = 20) -> Dict[str, Dict]:
        """Search by installed program name."""
        results = {}
        
        try:
            cmd = [
                'nix-search',
                '--program', program,
                '--channel', self.channel,
                '--max-results', str(limit),
                '--json'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {}
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    pkg = json.loads(line)
                    attr_name = pkg.get('package_attr_name', '')
                    if attr_name:
                        results[attr_name] = self._parse_package(pkg)
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"Error during nix-search: {e}")
        
        return results
    
    def _parse_package(self, pkg: Dict) -> Dict:
        """Parse nix-search-cli JSON output into our format."""
        description = pkg.get('package_description', '')
        
        # Format license
        license_info = pkg.get('package_license', [])
        if license_info and isinstance(license_info, list):
            license_str = license_info[0].get('fullName', 'unknown') if license_info else 'unknown'
        else:
            license_str = 'unknown'
        
        # Format homepage
        homepage = pkg.get('package_homepage', [])
        if isinstance(homepage, list):
            homepage = homepage[0] if homepage else ''
        
        return {
            'pname': pkg.get('package_pname', pkg.get('package_attr_name', '')),
            'version': pkg.get('package_pversion', 'unknown'),
            'description': description,
            'summary': description[:200] if description else '',
            'homepage': homepage,
            'license': license_str,
            'programs': pkg.get('package_programs', []),
            'outputs': pkg.get('package_outputs', ['out']),
        }
    
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
        
        # Search by exact name
        results = self.search_by_name(package_name, limit=5)
        
        # Look for exact match
        if package_name in results:
            self._cache[package_name] = results[package_name]
            return results[package_name]
        
        # Try partial match
        for name, info in results.items():
            if info.get('pname') == package_name:
                self._cache[package_name] = info
                return info
        
        return None
    
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
        
        # Try general search
        results = self.search([package_name], limit=5)
        if package_name in results:
            return (package_name, results[package_name].get('version', 'unknown'))
        
        # Check if any result is an exact pname match
        for name, info in results.items():
            if info.get('pname') == package_name:
                return (name, info.get('version', 'unknown'))
        
        return None
