#!/usr/bin/env python3
#
# Licensed under the GNU General Public License Version 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright (C) 2025-2026 PackageKit Nix Backend Contributors

"""
AppStream metadata generator for nixpkgs using Flathub data correlation.

This module:
1. Loads prepackaged nixpkgs application metadata (from nixpkgs-apps.json)
2. Downloads AppStream metadata from Flathub
3. Correlates nixpkgs packages with Flathub components via intelligent matching
4. Generates merged AppStream catalog with nixpkgs versions but Flathub metadata

The nixpkgs-apps.json file should be regenerated periodically on a machine
with access to nixpkgs source. This avoids runtime dependency on nix-search
or package building.

Usage:
    python appstream.py generate --output ./appstream-data
    python appstream.py info firefox
    python appstream.py match org.videolan.VLC
    python appstream.py correlate --report ./correlation-report.json
    python appstream.py refresh --output ./nixpkgs-apps.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

import tldextract

# Flathub AppStream data URLs
FLATHUB_APPSTREAM_URL = "https://dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz"
FLATHUB_ICONS_BASE_URL = "https://dl.flathub.org/repo/appstream/x86_64/icons"

# Default cache directory
DEFAULT_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "nix-appstream"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class NixPackage:
	"""Represents a nixpkgs package with metadata for correlation."""

	attr: str  # e.g., "firefox"
	pname: str  # e.g., "firefox"
	version: str
	description: str = ""
	homepage: str = ""
	license: str = ""


@dataclass
class FlathubComponent:
	"""Represents an AppStream component from Flathub."""

	id: str  # e.g., "org.mozilla.firefox"
	name: str
	summary: str
	description: str
	categories: list[str] = field(default_factory=list)
	keywords: list[str] = field(default_factory=list)
	screenshots: list[str] = field(default_factory=list)
	icon_url: str | None = None
	icon_cached: str | None = None
	homepage: str | None = None
	developer_name: str | None = None
	raw_xml: str = ""


@dataclass
class AppStreamMapping:
	"""Mapping between a Flathub component and nixpkgs package."""

	flathub_id: str
	nixpkgs_attr: str
	nixpkgs_version: str
	confidence: float = 1.0  # 1.0 = exact match, <1.0 = heuristic
	match_reason: str = ""  # Description of why this matched


# =============================================================================
# Nixpkgs Data Loader (prepackaged data)
# =============================================================================

# Default path for prepackaged nixpkgs data
DEFAULT_NIXPKGS_DATA = Path(__file__).parent / "nixpkgs-apps.json"


class NixpkgsLoader:
	"""
	Loads prepackaged nixpkgs application data.

	The data file should be generated periodically on a machine with
	access to nixpkgs source, using the companion script that queries
	package metadata directly.
	"""

	def __init__(self, data_file: Path = DEFAULT_NIXPKGS_DATA):
		"""
		Initialize the loader.

		Args:
		    data_file: Path to prepackaged JSON data
		"""
		self.data_file = data_file
		self._packages: dict[str, NixPackage] = {}

	def load(self) -> dict[str, NixPackage]:
		"""
		Load packages from the prepackaged data file.

		Returns:
		    Dict mapping package attr to NixPackage
		"""
		if self._packages:
			return self._packages

		if not self.data_file.exists():
			print(f"Warning: Nixpkgs data file not found: {self.data_file}", file=sys.stderr)
			print("Run 'nix-appstream refresh' on a machine with nixpkgs access", file=sys.stderr)
			return {}

		print(f"Loading nixpkgs data from {self.data_file}...")

		with open(self.data_file) as f:
			data = json.load(f)

		packages_data = data.get("packages", {})
		for attr, pkg_data in packages_data.items():
			if not attr:
				continue

			self._packages[attr] = NixPackage(
				attr=attr,
				pname=pkg_data.get("pname", attr),
				version=pkg_data.get("version", "unknown"),
				description=pkg_data.get("description", ""),
				homepage=pkg_data.get("homepage", ""),
				license=pkg_data.get("license", "unknown"),
			)

		print(f"Loaded {len(self._packages)} packages")
		return self._packages

	def get_package(self, attr: str) -> NixPackage | None:
		"""Get a specific package by attribute name."""
		if not self._packages:
			self.load()
		return self._packages.get(attr)


# =============================================================================
# Flathub AppStream Fetcher
# =============================================================================


class FlathubFetcher:
	"""Downloads and parses Flathub AppStream data."""

	def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
		"""
		Initialize the fetcher.

		Args:
		    cache_dir: Directory for caching downloaded data
		"""
		self.cache_dir = cache_dir
		self.cache_dir.mkdir(parents=True, exist_ok=True)

	def fetch_appstream_data(self, max_age_hours: int = 24) -> Path:
		"""
		Download and cache Flathub AppStream data.

		Args:
		    max_age_hours: Maximum cache age in hours before re-downloading

		Returns:
		    Path to the decompressed XML file
		"""
		gz_path = self.cache_dir / "flathub-appstream.xml.gz"
		xml_path = self.cache_dir / "flathub-appstream.xml"

		# Check if we have a recent cache
		if xml_path.exists():
			import time

			age_hours = (time.time() - xml_path.stat().st_mtime) / 3600
			if age_hours < max_age_hours:
				print(f"Using cached Flathub data (age: {age_hours:.1f}h)")
				return xml_path

		print("Downloading Flathub AppStream data...")
		urllib.request.urlretrieve(FLATHUB_APPSTREAM_URL, gz_path)

		print("Decompressing...")
		with gzip.open(gz_path, "rb") as f_in:
			with open(xml_path, "wb") as f_out:
				f_out.write(f_in.read())

		return xml_path

	def parse_appstream(self, xml_path: Path) -> dict[str, FlathubComponent]:
		"""
		Parse Flathub AppStream XML into components.

		Args:
		    xml_path: Path to the AppStream XML file

		Returns:
		    Dict mapping component ID (desktop ID) to FlathubComponent
		"""
		print(f"Parsing {xml_path}...")
		components: dict[str, FlathubComponent] = {}

		tree = ET.parse(xml_path)
		root = tree.getroot()

		for component in root.findall(".//component"):
			# Only process desktop applications
			comp_type = component.get("type", "")
			if comp_type != "desktop-application":
				continue

			# Get component ID
			id_elem = component.find("id")
			if id_elem is None or not id_elem.text:
				continue

			comp_id = id_elem.text
			# Normalize ID (remove .desktop suffix if present)
			if comp_id.endswith(".desktop"):
				comp_id = comp_id[:-8]

			# Extract metadata
			name_elem = component.find("name")
			summary_elem = component.find("summary")
			desc_elem = component.find("description")

			# Get description text (may have nested <p> tags)
			description = ""
			if desc_elem is not None:
				desc_parts = []
				for p in desc_elem.findall("p"):
					if p.text:
						desc_parts.append(p.text)
				description = "\n\n".join(desc_parts)
				if not description and desc_elem.text:
					description = desc_elem.text

			# Get categories
			categories = []
			for cat in component.findall(".//category"):
				if cat.text:
					categories.append(cat.text)

			# Get keywords
			keywords = []
			for kw in component.findall(".//keyword"):
				if kw.text:
					keywords.append(kw.text)

			# Get screenshots
			screenshots = []
			for screenshot in component.findall(".//screenshot/image"):
				if screenshot.text and screenshot.get("type") == "source":
					screenshots.append(screenshot.text)

			# Get icon
			icon_url = None
			icon_cached = None
			for icon in component.findall("icon"):
				icon_type = icon.get("type", "")
				if icon_type == "remote" and icon.text:
					icon_url = icon.text
				elif icon_type == "cached" and icon.text:
					icon_cached = icon.text

			# Get homepage
			homepage = None
			for url in component.findall("url"):
				if url.get("type") == "homepage" and url.text:
					homepage = url.text
					break

			# Get developer name
			developer_name = None
			dev_elem = component.find("developer_name")
			if dev_elem is not None and dev_elem.text:
				developer_name = dev_elem.text

			# Store raw XML for later transformation
			raw_xml = ET.tostring(component, encoding="unicode")

			components[comp_id] = FlathubComponent(
				id=comp_id,
				name=name_elem.text if name_elem is not None and name_elem.text else comp_id,
				summary=summary_elem.text if summary_elem is not None and summary_elem.text else "",
				description=description,
				categories=categories,
				keywords=keywords,
				screenshots=screenshots,
				icon_url=icon_url,
				icon_cached=icon_cached,
				homepage=homepage,
				developer_name=developer_name,
				raw_xml=raw_xml,
			)

		print(f"Parsed {len(components)} desktop applications from Flathub")
		return components

	def download_icon(
		self,
		component: FlathubComponent,
		output_dir: Path,
		sizes: list[str] | None = None,
	) -> dict[str, Path]:
		"""
		Download icons for a component.

		Args:
		    component: FlathubComponent to download icons for
		    output_dir: Base output directory for icons
		    sizes: Icon sizes to download (default: ["64x64", "128x128"])

		Returns:
		    Dict mapping size to downloaded icon path
		"""
		if sizes is None:
			sizes = ["64x64", "128x128"]

		downloaded = {}

		for size in sizes:
			icon_dir = output_dir / "icons" / size
			icon_dir.mkdir(parents=True, exist_ok=True)

			# Try cached icon first
			if component.icon_cached:
				icon_filename = component.icon_cached
				if not icon_filename.endswith((".png", ".svg")):
					icon_filename += ".png"

				icon_url = f"{FLATHUB_ICONS_BASE_URL}/{size}/{icon_filename}"
				icon_path = icon_dir / f"{component.id}.png"

				try:
					urllib.request.urlretrieve(icon_url, icon_path)
					downloaded[size] = icon_path
				except Exception:
					pass

			# Fall back to remote icon
			elif component.icon_url:
				ext = ".svg" if component.icon_url.endswith(".svg") else ".png"
				icon_path = icon_dir / f"{component.id}{ext}"

				try:
					urllib.request.urlretrieve(component.icon_url, icon_path)
					downloaded[size] = icon_path
				except Exception:
					pass

		return downloaded


# =============================================================================
# Correlation Engine - Intelligent Matching
# =============================================================================


class CorrelationEngine:
	"""
	Correlates nixpkgs packages with Flathub components using intelligent matching.

	Matching Strategy:
	1. Match pname with last part of Flathub ID (e.g., firefox ↔ org.mozilla.firefox)
	2. Match homepage domain with Flathub ID parts (e.g., mozilla.com ↔ org.mozilla.*)
	3. Special handling for GitHub/GitLab URLs (username matching)
	4. Known manual mappings as fallback
	"""

	# Git hosting platforms that need special URL handling
	GIT_PLATFORMS: ClassVar[dict[str, str]] = {
		"github": "io.github",
		"gitlab": "io.gitlab",
		"codeberg": "org.codeberg",
		"sourceforge": "net.sourceforge",
		"bitbucket": "io.bitbucket",
	}

	# Special subdomains for git platforms
	GIT_SUBDOMAINS: ClassVar[dict[tuple[str, str], str]] = {
		("gitlab", "gnome"): "org.gnome",
		("gitlab", "freedesktop"): "org.freedesktop",
		("pages", "srht"): "io.srht",
	}

	def __init__(self):
		"""Initialize the correlation engine."""
		self._known_mappings: dict[str, str] = {}  # flathub_id -> nixpkgs_attr

	def add_known_mapping(self, flathub_id: str, nixpkgs_attr: str):
		"""Add a known mapping between Flathub ID and nixpkgs attr."""
		self._known_mappings[flathub_id] = nixpkgs_attr

	def load_known_mappings(self, mappings_file: Path):
		"""Load known mappings from a JSON file."""
		if mappings_file.exists():
			with open(mappings_file) as f:
				data = json.load(f)
				# Filter out comment keys
				for k, v in data.items():
					if not k.startswith("_"):
						self._known_mappings[k] = v

	def correlate(
		self,
		flathub_components: dict[str, FlathubComponent],
		nixpkgs_packages: dict[str, NixPackage],
	) -> list[AppStreamMapping]:
		"""
		Correlate Flathub components with nixpkgs packages.

		Uses intelligent matching based on pname and homepage analysis.
		Known mappings are applied as overrides for cases where auto-matching fails.

		Args:
		    flathub_components: Dict of flathub_id -> FlathubComponent
		    nixpkgs_packages: Dict of attr -> NixPackage

		Returns:
		    List of AppStreamMapping objects
		"""
		mappings: list[AppStreamMapping] = []
		matched_flathub_ids: set[str] = set()
		matched_nix_attrs: set[str] = set()

		# Build indexes for efficient matching
		pname_to_packages: dict[str, list[NixPackage]] = {}
		for pkg in nixpkgs_packages.values():
			pname_lower = pkg.pname.lower()
			if pname_lower not in pname_to_packages:
				pname_to_packages[pname_lower] = []
			pname_to_packages[pname_lower].append(pkg)

		# Strategy 1: Automatic pname + homepage matching
		for flathub_id, _component in flathub_components.items():
			# Parse Flathub ID parts
			flathub_parts = flathub_id.lower().split(".")
			if len(flathub_parts) < 2:
				continue

			flathub_name = flathub_parts[-1]  # e.g., "firefox" from "org.mozilla.firefox"

			# Try to find matching nixpkgs package
			match = self._find_best_match(
				flathub_id,
				flathub_parts,
				flathub_name,
				pname_to_packages,
				nixpkgs_packages,
				matched_nix_attrs,
			)

			if match:
				pkg, confidence, reason = match
				mappings.append(
					AppStreamMapping(
						flathub_id=flathub_id,
						nixpkgs_attr=pkg.attr,
						nixpkgs_version=pkg.version,
						confidence=confidence,
						match_reason=reason,
					)
				)
				matched_flathub_ids.add(flathub_id)
				matched_nix_attrs.add(pkg.attr)

		# Strategy 2: Apply known mappings as overrides
		# These fix incorrect auto-matches or add missing mappings
		for flathub_id, nixpkgs_attr in self._known_mappings.items():
			if flathub_id not in flathub_components or nixpkgs_attr not in nixpkgs_packages:
				continue

			pkg = nixpkgs_packages[nixpkgs_attr]

			# Check if we already have a mapping for this flathub_id
			existing_idx = None
			for i, m in enumerate(mappings):
				if m.flathub_id == flathub_id:
					existing_idx = i
					break

			new_mapping = AppStreamMapping(
				flathub_id=flathub_id,
				nixpkgs_attr=nixpkgs_attr,
				nixpkgs_version=pkg.version,
				confidence=1.0,
				match_reason="override mapping",
			)

			if existing_idx is not None:
				# Replace existing mapping (override)
				old_attr = mappings[existing_idx].nixpkgs_attr
				if old_attr != nixpkgs_attr:
					matched_nix_attrs.discard(old_attr)
				mappings[existing_idx] = new_mapping
			else:
				# Add new mapping
				mappings.append(new_mapping)
				matched_flathub_ids.add(flathub_id)

			matched_nix_attrs.add(nixpkgs_attr)

		# Sort by confidence
		mappings.sort(key=lambda m: (-m.confidence, m.flathub_id))

		return mappings

	def _find_best_match(
		self,
		flathub_id: str,
		flathub_parts: list[str],
		flathub_name: str,
		pname_to_packages: dict[str, list[NixPackage]],
		nixpkgs_packages: dict[str, NixPackage],
		matched_attrs: set[str],
	) -> tuple[NixPackage, float, str] | None:
		"""
		Find the best matching nixpkgs package for a Flathub component.

		Returns:
		    Tuple of (NixPackage, confidence, reason) or None
		"""
		candidates: list[tuple[NixPackage, float, str]] = []

		# Check pname matches
		if flathub_name in pname_to_packages:
			for pkg in pname_to_packages[flathub_name]:
				if pkg.attr in matched_attrs:
					continue

				# Verify with homepage if available
				homepage_match = self._check_homepage_match(pkg.homepage, flathub_parts)

				if homepage_match:
					# Both pname and homepage match - high confidence
					candidates.append((pkg, 0.95, f"pname '{flathub_name}' + homepage match"))
				else:
					# Only pname matches - medium confidence
					candidates.append((pkg, 0.7, f"pname '{flathub_name}' match"))

		# Also check if attr name matches (sometimes different from pname)
		for pkg in nixpkgs_packages.values():
			if pkg.attr in matched_attrs:
				continue
			if pkg.attr.lower() == flathub_name:
				homepage_match = self._check_homepage_match(pkg.homepage, flathub_parts)
				if homepage_match:
					candidates.append((pkg, 0.9, f"attr '{flathub_name}' + homepage match"))
				elif pkg.pname.lower() != flathub_name:  # Don't duplicate pname matches
					candidates.append((pkg, 0.6, f"attr '{flathub_name}' match"))

		# Return best candidate
		if candidates:
			candidates.sort(key=lambda x: -x[1])
			return candidates[0]

		return None

	def _check_homepage_match(self, homepage: str, flathub_parts: list[str]) -> bool:
		"""
		Check if a homepage URL matches the Flathub ID structure.

		Uses tldextract for proper URL domain parsing.

		Examples:
		- homepage="https://mozilla.com/firefox" matches org.mozilla.firefox
		- homepage="https://github.com/alainm23/planify" matches io.github.alainm23.planify

		Args:
		    homepage: Package homepage URL
		    flathub_parts: Flathub ID split by dots (lowercase)

		Returns:
		    True if homepage correlates with Flathub ID
		"""
		if not homepage:
			return False

		try:
			# Parse URL using tldextract for proper domain handling
			ext = tldextract.extract(homepage)
			parsed = urlparse(homepage)
			path_parts = [p for p in parsed.path.split("/") if p]

			domain = ext.domain.lower()
			subdomain = ext.subdomain.lower() if ext.subdomain else ""

			# Check for special subdomain combinations (e.g., gitlab.gnome.org)
			for (sub, dom), flathub_prefix in self.GIT_SUBDOMAINS.items():
				if subdomain == sub and domain == dom:
					# For these, check username in path
					if path_parts and len(flathub_parts) >= 3:
						username = path_parts[0].lower()
						expected_prefix = flathub_prefix.split(".")
						if (
							flathub_parts[: len(expected_prefix)] == expected_prefix
							and len(flathub_parts) > len(expected_prefix)
							and flathub_parts[len(expected_prefix)] == username
						):
							return True
					# Also check just the platform prefix
					if ".".join(flathub_parts[:2]) == flathub_prefix:
						return True
					return False

			# Check for git platform special handling
			if domain in self.GIT_PLATFORMS:
				flathub_prefix = self.GIT_PLATFORMS[domain]
				# For GitHub/GitLab, check username in path
				# e.g., github.com/alainm23/planify -> io.github.alainm23.planify
				if path_parts and len(flathub_parts) >= 3:
					username = path_parts[0].lower()
					expected_prefix = flathub_prefix.split(".")
					if (
						flathub_parts[: len(expected_prefix)] == expected_prefix
						and len(flathub_parts) > len(expected_prefix)
						and flathub_parts[len(expected_prefix)] == username
					):
						return True
				# Also check just the platform prefix
				if ".".join(flathub_parts[:2]) == flathub_prefix:
					return True
				return False

			# Standard domain matching
			# Check if domain appears in Flathub ID
			# e.g., "mozilla" should be in ["org", "mozilla", "firefox"]
			if domain in flathub_parts[:-1]:  # Don't match the app name itself
				return True

			# Also check subdomain if present
			if subdomain and subdomain not in ("www",) and subdomain in flathub_parts[:-1]:
				return True

			return False

		except Exception:
			return False

	def _parse_flathub_id(self, flathub_id: str) -> dict:
		"""Parse a Flathub ID into its components."""
		parts = flathub_id.split(".")
		return {
			"full": flathub_id,
			"parts": parts,
			"name": parts[-1] if parts else "",
			"domain": ".".join(parts[:-1]) if len(parts) > 1 else "",
		}


# =============================================================================
# AppStream Catalog Generator
# =============================================================================


class AppStreamGenerator:
	"""Generates AppStream catalog from correlated data."""

	def __init__(self, output_dir: Path):
		"""
		Initialize the generator.

		Args:
		    output_dir: Output directory for generated data
		"""
		self.output_dir = output_dir
		self.output_dir.mkdir(parents=True, exist_ok=True)

	def generate_catalog(
		self,
		mappings: list[AppStreamMapping],
		flathub_components: dict[str, FlathubComponent],
		nixpkgs_packages: dict[str, NixPackage],
		download_icons: bool = True,
		fetcher: FlathubFetcher | None = None,
	) -> Path:
		"""
		Generate AppStream catalog XML.

		Merges Flathub metadata with nixpkgs version/package info.

		Args:
		    mappings: List of correlations
		    flathub_components: Flathub component data
		    nixpkgs_packages: Nixpkgs package data
		    download_icons: Whether to download icons
		    fetcher: FlathubFetcher for icon downloads

		Returns:
		    Path to generated catalog
		"""
		print(f"Generating AppStream catalog with {len(mappings)} components...")

		# Create XML structure
		root = ET.Element("components")
		root.set("version", "0.16")
		root.set("origin", "nixpkgs")

		icon_count = 0

		for mapping in mappings:
			component = flathub_components.get(mapping.flathub_id)
			if not component:
				continue

			# Get nixpkgs info if available
			nix_info = None
			for pkg in nixpkgs_packages.values():
				if pkg.attr == mapping.nixpkgs_attr:
					nix_info = pkg
					break

			# Transform component XML
			try:
				transformed = self._transform_component(component, mapping, nix_info)
				comp_elem = ET.fromstring(transformed)
				root.append(comp_elem)

				# Download icons
				if download_icons and fetcher:
					icons = fetcher.download_icon(component, self.output_dir)
					if icons:
						icon_count += 1

			except ET.ParseError as e:
				print(f"Error parsing component {mapping.flathub_id}: {e}", file=sys.stderr)
				continue

		# Write catalog
		xml_dir = self.output_dir / "swcatalog" / "xml"
		xml_dir.mkdir(parents=True, exist_ok=True)

		catalog_path = xml_dir / "nixpkgs.xml"
		tree = ET.ElementTree(root)
		ET.indent(tree, space="  ")
		tree.write(catalog_path, encoding="unicode", xml_declaration=True)

		# Compress
		with open(catalog_path, "rb") as f_in:
			with gzip.open(str(catalog_path) + ".gz", "wb") as f_out:
				f_out.write(f_in.read())

		print(f"Generated catalog: {catalog_path}.gz")
		print(f"Downloaded {icon_count} icons")

		# Move icons to standard location
		icons_src = self.output_dir / "icons"
		icons_dst = self.output_dir / "swcatalog" / "icons" / "nixpkgs"
		if icons_src.exists():
			icons_dst.parent.mkdir(parents=True, exist_ok=True)
			if icons_dst.exists():
				import shutil

				shutil.rmtree(icons_dst)
			icons_src.rename(icons_dst)

		return catalog_path

	def _transform_component(
		self,
		component: FlathubComponent,
		mapping: AppStreamMapping,
		nix_info: NixPackage | None,
	) -> str:
		"""
		Transform a Flathub component for nixpkgs.

		Changes:
		- Sets <pkgname> to nixpkgs attribute
		- Updates version to nixpkgs version
		- Updates icon paths to local
		"""
		elem = ET.fromstring(component.raw_xml)

		# Update or add pkgname (nixpkgs attribute)
		# Strip common prefixes like "nixos." that nix-env -qaP adds but aren't used
		# in actual package commands like "nix profile install nixpkgs#firefox"
		pkgname = elem.find("pkgname")
		if pkgname is None:
			pkgname = ET.SubElement(elem, "pkgname")
		pkg_attr = mapping.nixpkgs_attr
		# Remove nixos. prefix if present (from nix-env -qaP output)
		if pkg_attr.startswith("nixos."):
			pkg_attr = pkg_attr[6:]  # len("nixos.") = 6
		pkgname.text = pkg_attr

		# Don't include version/releases in AppStream data
		# Version should come from PackageKit backend dynamically:
		# - nix-search for available packages
		# - manifest.json for installed packages
		# Remove any existing releases section to keep metadata static
		releases = elem.find("releases")
		if releases is not None:
			elem.remove(releases)

		# Update icon to local path
		for icon in elem.findall("icon"):
			icon_type = icon.get("type", "")
			if icon_type == "cached" and icon.text:
				# Point to our local icons
				icon.set("type", "cached")
				icon.get("width", "128")
				icon.get("height", "128")
				icon.text = f"{component.id}.png"

		# If we have nixpkgs-specific info, we could override description etc.
		# But generally we defer to Flathub's richer metadata

		return ET.tostring(elem, encoding="unicode")

	def generate_report(
		self,
		mappings: list[AppStreamMapping],
		flathub_components: dict[str, FlathubComponent],
		output_path: Path | None = None,
	) -> dict:
		"""
		Generate a JSON report of the correlation results.

		Args:
		    mappings: List of correlations
		    flathub_components: Flathub components for stats
		    output_path: Optional path to write report

		Returns:
		    Report dictionary
		"""
		report = {
			"total_flathub_components": len(flathub_components),
			"total_mappings": len(mappings),
			"coverage_percent": (len(mappings) / len(flathub_components) * 100) if flathub_components else 0,
			"by_confidence": {
				"override": len([m for m in mappings if m.confidence == 1.0]),
				"high": len([m for m in mappings if 0.9 <= m.confidence < 1.0]),
				"medium": len([m for m in mappings if 0.6 <= m.confidence < 0.9]),
				"low": len([m for m in mappings if m.confidence < 0.6]),
			},
			"mappings": [
				{
					"flathub_id": m.flathub_id,
					"nixpkgs_attr": m.nixpkgs_attr,
					"version": m.nixpkgs_version,
					"confidence": m.confidence,
					"name": flathub_components.get(
						m.flathub_id, FlathubComponent(m.flathub_id, "", "", "")
					).name,
				}
				for m in mappings
			],
			"unmapped_popular": [
				{"id": comp.id, "name": comp.name}
				for comp_id, comp in list(flathub_components.items())[:200]
				if not any(m.flathub_id == comp_id for m in mappings)
			][:50],
		}

		if output_path:
			with open(output_path, "w") as f:
				json.dump(report, f, indent=2)
			print(f"Generated report: {output_path}")

		return report


# =============================================================================
# Main Workflow
# =============================================================================


def generate_appstream(
	output_dir: Path,
	cache_dir: Path = DEFAULT_CACHE_DIR,
	download_icons: bool = True,
	mappings_file: Path | None = None,
	nixpkgs_data: Path | None = None,
) -> Path:
	"""
	Main workflow to generate AppStream data.

	This uses intelligent correlation between prepackaged nixpkgs metadata
	and Flathub components - no package building required!

	Args:
	    output_dir: Output directory for generated data
	    cache_dir: Cache directory for downloads
	    download_icons: Whether to download icons
	    mappings_file: Optional JSON file with known flathub_id -> attr mappings
	    nixpkgs_data: Path to prepackaged nixpkgs JSON data

	Returns:
	    Path to generated catalog
	"""
	# Initialize components
	loader = NixpkgsLoader(nixpkgs_data) if nixpkgs_data else NixpkgsLoader()
	fetcher = FlathubFetcher(cache_dir)
	correlator = CorrelationEngine()
	generator = AppStreamGenerator(output_dir)

	# Load known mappings if provided
	if mappings_file:
		correlator.load_known_mappings(mappings_file)

	# Fetch Flathub data
	print("=" * 60)
	print("Step 1: Fetching Flathub AppStream data")
	print("=" * 60)
	xml_path = fetcher.fetch_appstream_data()
	flathub_components = fetcher.parse_appstream(xml_path)

	# Load prepackaged nixpkgs metadata
	print()
	print("=" * 60)
	print("Step 2: Loading nixpkgs metadata")
	print("=" * 60)
	nixpkgs_packages = loader.load()

	# Correlate using intelligent matching
	print()
	print("=" * 60)
	print("Step 3: Correlating packages (pname + homepage matching)")
	print("=" * 60)
	mappings = correlator.correlate(flathub_components, nixpkgs_packages)
	print(f"Created {len(mappings)} mappings")

	# Show some stats
	high_conf = len([m for m in mappings if m.confidence >= 0.9])
	med_conf = len([m for m in mappings if 0.7 <= m.confidence < 0.9])
	low_conf = len([m for m in mappings if m.confidence < 0.7])
	print(f"  - High confidence (≥0.9): {high_conf}")
	print(f"  - Medium confidence (0.7-0.9): {med_conf}")
	print(f"  - Low confidence (<0.7): {low_conf}")

	# Generate catalog
	print()
	print("=" * 60)
	print("Step 4: Generating AppStream catalog")
	print("=" * 60)
	catalog_path = generator.generate_catalog(
		mappings,
		flathub_components,
		nixpkgs_packages,
		download_icons=download_icons,
		fetcher=fetcher,
	)

	# Generate report
	report_path = output_dir / "correlation-report.json"
	report = generator.generate_report(mappings, flathub_components, report_path)
	print(f"Coverage: {report['coverage_percent']:.1f}%")

	return catalog_path


# =============================================================================
# CLI Entry Points
# =============================================================================


def cmd_generate(args):
	"""Generate AppStream data."""
	mappings_file = Path(args.mappings) if args.mappings and Path(args.mappings).exists() else None
	nixpkgs_data = Path(args.nixpkgs_data) if args.nixpkgs_data else None

	generate_appstream(
		output_dir=Path(args.output),
		cache_dir=Path(args.cache_dir),
		download_icons=not args.no_icons,
		mappings_file=mappings_file,
		nixpkgs_data=nixpkgs_data,
	)


def cmd_info(args):
	"""Show info about a nixpkgs package."""
	nixpkgs_data = Path(args.nixpkgs_data) if args.nixpkgs_data else None
	loader = NixpkgsLoader(nixpkgs_data) if nixpkgs_data else NixpkgsLoader()

	print(f"Looking up {args.package}...")
	pkg = loader.get_package(args.package)

	if pkg:
		print(f"\nPackage: {pkg.attr}")
		print(f"  pname: {pkg.pname}")
		print(f"  version: {pkg.version}")
		print(f"  homepage: {pkg.homepage}")
		print(f"  license: {pkg.license}")
		print(
			f"  description: {pkg.description[:200]}..."
			if len(pkg.description) > 200
			else f"  description: {pkg.description}"
		)
	else:
		print(f"Package '{args.package}' not found")


def cmd_match(args):
	"""Test correlation for a specific Flathub ID."""
	cache_dir = Path(args.cache_dir)
	nixpkgs_data = Path(args.nixpkgs_data) if args.nixpkgs_data else None
	loader = NixpkgsLoader(nixpkgs_data) if nixpkgs_data else NixpkgsLoader()
	fetcher = FlathubFetcher(cache_dir)
	correlator = CorrelationEngine()

	if args.mappings and Path(args.mappings).exists():
		correlator.load_known_mappings(Path(args.mappings))

	# Fetch Flathub data
	print("Fetching Flathub data...")
	xml_path = fetcher.fetch_appstream_data()
	flathub_components = fetcher.parse_appstream(xml_path)

	if args.flathub_id not in flathub_components:
		print(f"Flathub ID '{args.flathub_id}' not found")
		return

	component = flathub_components[args.flathub_id]
	print(f"\nFlathub component: {args.flathub_id}")
	print(f"  Name: {component.name}")
	print(f"  Summary: {component.summary}")

	# Load nixpkgs packages
	print("\nLoading nixpkgs data...")
	nixpkgs_packages = loader.load()

	# Try to correlate just this one
	mappings = correlator.correlate({args.flathub_id: component}, nixpkgs_packages)

	if mappings:
		m = mappings[0]
		print("\n✓ Match found!")
		print(f"  nixpkgs attr: {m.nixpkgs_attr}")
		print(f"  version: {m.nixpkgs_version}")
		print(f"  confidence: {m.confidence:.2f}")
		print(f"  reason: {m.match_reason}")

		# Show the nixpkgs package details
		if m.nixpkgs_attr in nixpkgs_packages:
			pkg = nixpkgs_packages[m.nixpkgs_attr]
			print(f"\n  nixpkgs homepage: {pkg.homepage}")
	else:
		print("\n✗ No match found")

		# Show what we tried to match
		flathub_parts = args.flathub_id.lower().split(".")
		print(f"\n  Flathub ID parts: {flathub_parts}")
		print(f"  Looking for pname: {flathub_parts[-1]}")


def cmd_correlate(args):
	"""Run correlation and generate report only."""
	cache_dir = Path(args.cache_dir)
	nixpkgs_data = Path(args.nixpkgs_data) if args.nixpkgs_data else None
	loader = NixpkgsLoader(nixpkgs_data) if nixpkgs_data else NixpkgsLoader()
	fetcher = FlathubFetcher(cache_dir)
	correlator = CorrelationEngine()

	if args.mappings and Path(args.mappings).exists():
		correlator.load_known_mappings(Path(args.mappings))

	# Fetch and parse Flathub
	print("Fetching Flathub data...")
	xml_path = fetcher.fetch_appstream_data()
	flathub_components = fetcher.parse_appstream(xml_path)

	# Load nixpkgs
	print("Loading nixpkgs data...")
	nixpkgs_packages = loader.load()

	# Run correlation
	print("Running correlation...")
	mappings = correlator.correlate(flathub_components, nixpkgs_packages)

	# Generate report
	output_path = Path(args.report)
	generator = AppStreamGenerator(output_path.parent)
	report = generator.generate_report(mappings, flathub_components, output_path)

	print(f"\nCoverage: {report['coverage_percent']:.1f}%")
	print(f"Report written to: {output_path}")


def cmd_refresh(args):
	"""Refresh nixpkgs-apps.json by querying local nixpkgs."""
	print("Querying local nixpkgs for package metadata...")
	print("This may take a minute or two...")

	# Use nix-env to query all packages with JSON output
	# This gives us: name, pname, version, description, meta.homepage, meta.license
	nixpkgs_arg = []
	if hasattr(args, "nixpkgs") and args.nixpkgs:
		nixpkgs_arg = ["-f", args.nixpkgs]

	try:
		result = subprocess.run(
			["nix-env", *nixpkgs_arg, "-qaP", "--json", "--meta"],
			capture_output=True,
			text=True,
			check=True,
		)
	except subprocess.CalledProcessError as e:
		print(f"Error querying nixpkgs: {e.stderr}")
		sys.exit(1)
	except FileNotFoundError:
		print("Error: nix-env not found. Make sure Nix is installed.")
		sys.exit(1)

	raw_packages = json.loads(result.stdout)
	print(f"Found {len(raw_packages)} total packages")

	# Filter to likely GUI applications
	# Heuristics: has a homepage, not a library (doesn't start with lib),
	# not a font, not a -unwrapped variant, etc.
	packages = {}
	skipped = {"no_pname": 0, "library": 0, "font": 0, "unwrapped": 0, "module": 0}

	for attr, data in raw_packages.items():
		meta = data.get("meta", {})
		pname = data.get("pname", "")

		# Skip packages without pname
		if not pname:
			skipped["no_pname"] += 1
			continue

		# Skip obvious non-applications
		pname_lower = pname.lower()
		if pname_lower.startswith("lib") and not pname_lower.startswith("libre"):
			skipped["library"] += 1
			continue
		if "font" in pname_lower or pname_lower.endswith("-fonts"):
			skipped["font"] += 1
			continue
		if pname_lower.endswith("-unwrapped"):
			skipped["unwrapped"] += 1
			continue
		if attr.startswith("python") and "Packages" in attr:
			skipped["module"] += 1
			continue
		if attr.startswith("perl") and "Packages" in attr:
			skipped["module"] += 1
			continue
		if attr.startswith("haskellPackages."):
			skipped["module"] += 1
			continue
		if attr.startswith("nodePackages."):
			skipped["module"] += 1
			continue
		if attr.startswith("rubyGems."):
			skipped["module"] += 1
			continue

		# Extract license info
		license_info = meta.get("license", {})
		if isinstance(license_info, list):
			license_names = [
				lic.get("shortName", lic.get("spdxId", "unknown")) if isinstance(lic, dict) else str(lic)
				for lic in license_info
			]
			license_str = " AND ".join(license_names)
		elif isinstance(license_info, dict):
			license_str = license_info.get("shortName", license_info.get("spdxId", "unknown"))
		else:
			license_str = str(license_info) if license_info else None

		packages[attr] = {
			"attr": attr,
			"pname": pname,
			"version": data.get("version", ""),
			"description": meta.get("description", ""),
			"homepage": meta.get("homepage", ""),
			"license": license_str,
		}

	print(f"Filtered to {len(packages)} candidate applications")
	print(f"Skipped: {skipped}")

	# Build output structure
	output = {
		"_meta": {
			"generated": datetime.now(UTC).isoformat(),
			"source": args.nixpkgs if hasattr(args, "nixpkgs") and args.nixpkgs else "default nixpkgs",
			"total_packages": len(raw_packages),
			"filtered_packages": len(packages),
		},
		"packages": packages,
	}

	# Write output
	output_path = Path(args.output)
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with open(output_path, "w") as f:
		json.dump(output, f, indent=2)

	print(f"\nWrote {len(packages)} packages to {output_path}")
	print(f"Total nixpkgs queried: {len(raw_packages)}")


def main():
	"""CLI entry point."""
	parser = argparse.ArgumentParser(
		description="Generate AppStream metadata for nixpkgs using Flathub correlation"
	)
	subparsers = parser.add_subparsers(dest="command", help="Available commands")

	# Common arguments
	def add_common_args(p):
		p.add_argument(
			"--nixpkgs-data",
			default=str(DEFAULT_NIXPKGS_DATA),
			help="Path to prepackaged nixpkgs JSON data",
		)

	# Generate command
	gen_parser = subparsers.add_parser("generate", help="Generate AppStream catalog")
	gen_parser.add_argument(
		"-o",
		"--output",
		default="./appstream-data",
		help="Output directory",
	)
	gen_parser.add_argument(
		"--cache-dir",
		default=str(DEFAULT_CACHE_DIR),
		help="Cache directory for downloads",
	)
	gen_parser.add_argument(
		"--no-icons",
		action="store_true",
		help="Skip downloading icons",
	)
	gen_parser.add_argument(
		"--mappings",
		default="known-mappings.json",
		help="JSON file with known flathub_id -> nixpkgs attr mappings",
	)
	add_common_args(gen_parser)
	gen_parser.set_defaults(func=cmd_generate)

	# Info command - show info about a nixpkgs package
	info_parser = subparsers.add_parser("info", help="Show info about a nixpkgs package")
	info_parser.add_argument("package", help="Package attribute to look up")
	add_common_args(info_parser)
	info_parser.set_defaults(func=cmd_info)

	# Match command - test correlation for a specific Flathub ID
	match_parser = subparsers.add_parser("match", help="Test correlation for a Flathub ID")
	match_parser.add_argument("flathub_id", help="Flathub ID to match (e.g., org.mozilla.firefox)")
	match_parser.add_argument(
		"--cache-dir",
		default=str(DEFAULT_CACHE_DIR),
		help="Cache directory for downloads",
	)
	match_parser.add_argument(
		"--mappings",
		default="known-mappings.json",
		help="JSON file with known flathub_id -> nixpkgs attr mappings",
	)
	add_common_args(match_parser)
	match_parser.set_defaults(func=cmd_match)

	# Correlate command - run full correlation and generate report
	corr_parser = subparsers.add_parser("correlate", help="Run correlation and generate report")
	corr_parser.add_argument(
		"-r",
		"--report",
		default="./correlation-report.json",
		help="Output report path",
	)
	corr_parser.add_argument(
		"--cache-dir",
		default=str(DEFAULT_CACHE_DIR),
		help="Cache directory for downloads",
	)
	corr_parser.add_argument(
		"--mappings",
		default="known-mappings.json",
		help="JSON file with known flathub_id -> nixpkgs attr mappings",
	)
	add_common_args(corr_parser)
	corr_parser.set_defaults(func=cmd_correlate)

	# Refresh command - regenerate nixpkgs-apps.json from local nixpkgs
	refresh_parser = subparsers.add_parser(
		"refresh", help="Refresh nixpkgs-apps.json by querying local nixpkgs"
	)
	refresh_parser.add_argument(
		"-o",
		"--output",
		default="./nixpkgs-apps.json",
		help="Output path for nixpkgs data JSON",
	)
	refresh_parser.add_argument(
		"--nixpkgs",
		help="Path to nixpkgs (optional, uses default if not specified)",
	)
	refresh_parser.set_defaults(func=cmd_refresh)

	args = parser.parse_args()

	if args.command is None:
		parser.print_help()
		sys.exit(1)

	args.func(args)


if __name__ == "__main__":
	main()
