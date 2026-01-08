#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Licensed under the GNU General Public License Version 2
#
# AppStream XML parser for nixos-appstream-data

"""
Parse AppStream XML files from nixos-appstream-data repository.

Extracts rich metadata including:
- Categories
- Icons (cached and stock)
- Screenshots
- Project license
- Launchable information
- Release information
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set


class AppStreamParser:
    """
    Parser for AppStream XML files from nixos-appstream-data.
    """
    
    def __init__(self, appstream_dir: Optional[str] = None):
        """
        Initialize parser.
        
        Args:
            appstream_dir: Path to nixos-appstream-data directory
                          If None, looks for submodule in backend directory
        """
        if appstream_dir is None:
            # Try to find the submodule
            backend_dir = Path(__file__).parent
            appstream_dir = backend_dir / 'nixos-appstream-data'
        
        self.appstream_dir = Path(appstream_dir)
        self.free_metadata = self.appstream_dir / 'free' / 'metadata'
        self.unfree_metadata = self.appstream_dir / 'unfree' / 'metadata'
        
        # Cache for parsed data
        self._package_cache: Dict[str, Dict] = {}
        self._category_index: Optional[Dict[str, Set[str]]] = None
    
    def _parse_xml_file(self, xml_path: Path) -> Optional[Dict]:
        """
        Parse a single AppStream XML file.
        
        Returns:
            Dictionary with AppStream metadata
        """
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Extract package name from filename (format: pkgname::appid.xml)
            filename = xml_path.name
            if '::' in filename:
                pkgname = filename.split('::')[0]
            else:
                pkgname = filename.replace('.xml', '')
            
            # Extract pkgname from XML if available
            pkgname_elem = root.find('pkgname')
            if pkgname_elem is not None and pkgname_elem.text:
                pkgname = pkgname_elem.text
            
            data = {
                'pkgname': pkgname,
                'id': self._get_text(root, 'id'),
                'name': self._get_text(root, 'name'),
                'summary': self._get_text(root, 'summary'),
                'description': self._get_description(root),
                'categories': self._get_categories(root),
                'icons': self._get_icons(root),
                'screenshots': self._get_screenshots(root),
                'urls': self._get_urls(root),
                'license': self._get_text(root, 'project_license'),
                'launchable': self._get_launchable(root),
                'component_type': root.get('type', 'desktop'),
            }
            
            return data
            
        except Exception as e:
            print(f"Warning: Failed to parse {xml_path}: {e}")
            return None
    
    def _get_text(self, root: ET.Element, tag: str) -> str:
        """Get text content of an element."""
        elem = root.find(tag)
        return elem.text if elem is not None and elem.text else ''
    
    def _get_description(self, root: ET.Element) -> str:
        """Extract description, converting from XML to plain text."""
        desc_elem = root.find('description')
        if desc_elem is None:
            return ''
        
        # Convert description XML to plain text
        parts = []
        for child in desc_elem:
            if child.tag == 'p':
                if child.text:
                    parts.append(child.text.strip())
            elif child.tag == 'ul':
                for li in child.findall('li'):
                    if li.text:
                        parts.append(f"• {li.text.strip()}")
            elif child.tag == 'ol':
                for i, li in enumerate(child.findall('li'), 1):
                    if li.text:
                        parts.append(f"{i}. {li.text.strip()}")
        
        return '\n'.join(parts)
    
    def _get_categories(self, root: ET.Element) -> List[str]:
        """Extract categories."""
        categories_elem = root.find('categories')
        if categories_elem is None:
            return []
        
        return [cat.text for cat in categories_elem.findall('category') 
                if cat.text]
    
    def _get_icons(self, root: ET.Element) -> List[Dict]:
        """Extract icon information."""
        icons = []
        for icon_elem in root.findall('icon'):
            icon = {
                'type': icon_elem.get('type', 'cached'),
                'width': int(icon_elem.get('width', 0)) if icon_elem.get('width') else None,
                'height': int(icon_elem.get('height', 0)) if icon_elem.get('height') else None,
                'name': icon_elem.text if icon_elem.text else '',
            }
            icons.append(icon)
        return icons
    
    def _get_screenshots(self, root: ET.Element) -> List[Dict]:
        """Extract screenshot information."""
        screenshots_elem = root.find('screenshots')
        if screenshots_elem is None:
            return []
        
        screenshots = []
        for ss in screenshots_elem.findall('screenshot'):
            screenshot = {
                'default': ss.get('type') == 'default',
                'images': []
            }
            
            for img in ss.findall('image'):
                screenshot['images'].append({
                    'type': img.get('type', 'source'),
                    'url': img.text if img.text else '',
                })
            
            screenshots.append(screenshot)
        
        return screenshots
    
    def _get_urls(self, root: ET.Element) -> Dict[str, str]:
        """Extract URLs (homepage, bugtracker, etc.)."""
        urls = {}
        for url_elem in root.findall('url'):
            url_type = url_elem.get('type', 'homepage')
            if url_elem.text:
                urls[url_type] = url_elem.text
        return urls
    
    def _get_launchable(self, root: ET.Element) -> Optional[str]:
        """Extract launchable desktop-id."""
        launch_elem = root.find('launchable')
        if launch_elem is not None and launch_elem.text:
            return launch_elem.text
        return None
    
    def get_package_appstream(self, pkgname: str, check_unfree: bool = True) -> Optional[Dict]:
        """
        Get AppStream data for a package.
        
        Args:
            pkgname: Package name (attribute)
            check_unfree: Whether to check unfree packages too
            
        Returns:
            Dictionary with AppStream metadata or None
        """
        # Check cache
        if pkgname in self._package_cache:
            return self._package_cache[pkgname]
        
        # Search in free metadata
        if self.free_metadata.exists():
            for xml_file in self.free_metadata.glob(f'{pkgname}::*.xml'):
                data = self._parse_xml_file(xml_file)
                if data:
                    self._package_cache[pkgname] = data
                    return data
        
        # Search in unfree metadata
        if check_unfree and self.unfree_metadata.exists():
            for xml_file in self.unfree_metadata.glob(f'{pkgname}::*.xml'):
                data = self._parse_xml_file(xml_file)
                if data:
                    self._package_cache[pkgname] = data
                    return data
        
        return None
    
    def build_category_index(self) -> Dict[str, Set[str]]:
        """
        Build an index of categories to package names.
        
        Returns:
            Dictionary mapping category names to sets of package names
        """
        if self._category_index is not None:
            return self._category_index
        
        self._category_index = {}
        
        # Index free packages
        if self.free_metadata.exists():
            for xml_file in self.free_metadata.glob('*.xml'):
                data = self._parse_xml_file(xml_file)
                if data:
                    pkgname = data['pkgname']
                    for category in data['categories']:
                        if category not in self._category_index:
                            self._category_index[category] = set()
                        self._category_index[category].add(pkgname)
        
        # Index unfree packages
        if self.unfree_metadata.exists():
            for xml_file in self.unfree_metadata.glob('*.xml'):
                data = self._parse_xml_file(xml_file)
                if data:
                    pkgname = data['pkgname']
                    for category in data['categories']:
                        if category not in self._category_index:
                            self._category_index[category] = set()
                        self._category_index[category].add(pkgname)
        
        return self._category_index
    
    def search_by_category(self, categories: List[str]) -> Set[str]:
        """
        Search for packages by categories.
        
        Args:
            categories: List of category names to search for
            
        Returns:
            Set of package names matching any of the categories
        """
        # Build index if needed
        if self._category_index is None:
            self.build_category_index()
        
        results = set()
        for category in categories:
            if category in self._category_index:
                results.update(self._category_index[category])
        
        return results
    
    def get_all_categories(self) -> List[str]:
        """Get all available categories."""
        if self._category_index is None:
            self.build_category_index()
        
        return sorted(self._category_index.keys())
