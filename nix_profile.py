#!/usr/bin/python3
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

Manifest Format Documentation:
-----------------------------
The nix profile manifest.json has evolved through multiple versions:

Version 2 (legacy):
  - elements: list of package objects
  - Each element has: attrPath, originalUrl, storePaths, url

Version 3 (current, Nix 2.4+):
  - elements: dict keyed by package name
  - Each element has: active, attrPath, originalUrl, outputs, priority, storePaths, url
  - attrPath format: "legacyPackages.<system>.<package>" (e.g., "legacyPackages.x86_64-linux.firefox")
"""

from __future__ import annotations

import json
import os
import pwd
from pathlib import Path
from typing import Literal, TypedDict, cast

# =============================================================================
# Type definitions for manifest.json structure
# =============================================================================


class ManifestElementV2(TypedDict, total=False):
	"""
	Package element in manifest v2 format.

	Example:
		{
			"attrPath": "firefox",
			"originalUrl": "flake:nixpkgs",
			"storePaths": ["/nix/store/abc123-firefox-122.0"],
			"url": "github:NixOS/nixpkgs/..."
		}
	"""

	attrPath: str
	originalUrl: str
	storePaths: list[str]
	url: str


class ManifestElementV3(TypedDict, total=False):
	"""
	Package element in manifest v3 format.

	Example:
		{
			"active": true,
			"attrPath": "legacyPackages.x86_64-linux.firefox",
			"originalUrl": "flake:nixpkgs",
			"outputs": null,
			"priority": 5,
			"storePaths": ["/nix/store/abc123-firefox-122.0"],
			"url": "path:/nix/store/..."
		}
	"""

	active: bool
	attrPath: str
	originalUrl: str
	outputs: list[str] | None
	priority: int
	storePaths: list[str]
	url: str


class ManifestV2(TypedDict, total=False):
	"""
	Manifest format version 2.

	Example:
		{
			"version": 2,
			"elements": [
				{"attrPath": "firefox", ...},
				{"attrPath": "vim", ...}
			]
		}
	"""

	version: Literal[1, 2]
	elements: list[ManifestElementV2]


class ManifestV3(TypedDict, total=False):
	"""
	Manifest format version 3 (Nix 2.4+).

	Example:
		{
			"version": 3,
			"elements": {
				"firefox": {"active": true, "attrPath": "legacyPackages.x86_64-linux.firefox", ...},
				"vim": {"active": true, "attrPath": "legacyPackages.x86_64-linux.vim", ...}
			}
		}
	"""

	version: Literal[3]
	elements: dict[str, ManifestElementV3]


# Union type for any manifest version
Manifest = ManifestV2 | ManifestV3

# Normalized elements dict (always v3 format)
NormalizedElements = dict[str, ManifestElementV3]


class PackageInfo(TypedDict):
	"""Normalized package information returned by get_package_info()."""

	attrPath: str
	originalUrl: str
	storePaths: list[str]
	url: str


class LoadedManifest(TypedDict):
	"""Result of loading and normalizing a manifest."""

	version: int
	elements: NormalizedElements


# =============================================================================
# NixProfile class
# =============================================================================


class NixProfile:
	"""
	Manager for the user's nix profile.
	Parses manifest.json and provides package information.
	"""

	def __init__(self, profile_path: str | None = None):
		"""
		Initialize the nix profile manager.

		Args:
			profile_path: Path to profile directory. Defaults to ~/.nix-profile
		"""
		if profile_path is None:
			profile_path = self._resolve_user_profile()

		self.profile_path = Path(profile_path)
		self.manifest_path = self.profile_path / "manifest.json"

	@staticmethod
	def _resolve_user_profile() -> str:
		"""
		Resolve the profile path for the requesting user.

		PackageKit runs as root but provides the UID of the requesting user
		via the UID environment variable. We use this to find the correct
		user's profile instead of root's profile.

		Returns:
			Path to the user's nix profile
		"""
		# PackageKit provides the requesting user's UID
		uid_str = os.environ.get("UID")
		if uid_str:
			try:
				uid = int(uid_str)
				pw_entry = pwd.getpwuid(uid)
				username = pw_entry.pw_name
				home_dir = pw_entry.pw_dir

				# Try the user's home profile first
				home_profile = os.path.join(home_dir, ".nix-profile")
				if os.path.exists(home_profile):
					return home_profile

				# Fall back to per-user profile location
				return f"/nix/var/nix/profiles/per-user/{username}/profile"
			except (ValueError, KeyError):
				pass  # Invalid UID, fall through to other methods

		# Fallback: try HOME environment variable
		home = os.environ.get("HOME")
		if home and home != "/root":
			return os.path.join(home, ".nix-profile")

		# Last resort: try SUDO_USER or USER
		username = os.environ.get("SUDO_USER") or os.environ.get("USER") or "root"
		return f"/nix/var/nix/profiles/per-user/{username}/profile"

	def _load_manifest(self) -> LoadedManifest | None:
		"""
		Load and normalize the manifest to v3 format.

		This method handles both v2 (list-based) and v3 (dict-based) manifest
		formats, normalizing v2 to v3 format for consistent downstream processing.

		Returns:
			LoadedManifest with normalized elements dict, or None if manifest
			doesn't exist or can't be parsed.
		"""
		if not self.manifest_path.exists():
			return None

		try:
			with open(self.manifest_path) as f:
				manifest = cast(Manifest, json.load(f))
		except (OSError, json.JSONDecodeError):
			return None

		version_num = manifest.get("version", 1)
		elements = manifest.get("elements", {})

		if version_num >= 3 and isinstance(elements, dict):
			# Already v3 format
			return {"version": version_num, "elements": elements}

		# Convert v2 (list) to v3 (dict) format
		if not isinstance(elements, list):
			return {"version": version_num, "elements": {}}

		normalized: NormalizedElements = {}
		for i, element in enumerate(elements):
			# Determine the package key
			attr_path = element.get("attrPath", "")
			if attr_path:
				pkg_key = attr_path
			else:
				original_url = element.get("originalUrl", "")
				if original_url and "#" in original_url:
					pkg_key = original_url.split("#")[-1]
				else:
					pkg_key = f"element-{i}"

			# Convert to v3 element format
			normalized[pkg_key] = {
				"active": True,
				"attrPath": attr_path,
				"originalUrl": element.get("originalUrl", ""),
				"outputs": None,
				"priority": 5,
				"storePaths": element.get("storePaths", []),
				"url": element.get("url", ""),
			}

		return {"version": version_num, "elements": normalized}

	def _get_package_name(self, pkg_key: str, element: ManifestElementV3) -> str:
		"""
		Extract the simple package name from an element.

		For v3, attrPath is like "legacyPackages.x86_64-linux.firefox" -> "firefox"
		For v2 (converted), attrPath is the simple name like "firefox"
		"""
		attr_path = element.get("attrPath", "")
		if attr_path and "." in attr_path:
			return attr_path.split(".")[-1]
		return attr_path or pkg_key

	def get_installed_packages(self) -> dict[str, str]:
		"""
		Get all installed packages with their versions.

		Returns:
			Dictionary mapping package attribute names to versions.
			Example: {'firefox': '122.0', 'vim': '9.0.1'}
		"""
		loaded = self._load_manifest()
		if not loaded:
			return {}

		packages = {}
		for pkg_key, element in loaded["elements"].items():
			if not element.get("active", True):
				continue

			pkg_name = self._get_package_name(pkg_key, element)
			store_paths = element.get("storePaths", [])
			version = "unknown"

			if store_paths:
				version = self._extract_version_from_store_path(store_paths[0], pkg_name)

			packages[pkg_name] = version

		return packages

	def find_package_index(self, package_name: str) -> str | None:
		"""
		Find the profile element identifier for a package.

		Args:
			package_name: Package attribute name

		Returns:
			Package key name (str) for use with nix profile remove/upgrade,
			or None if not found.
		"""
		loaded = self._load_manifest()
		if not loaded:
			return None

		for pkg_key, element in loaded["elements"].items():
			pkg_name = self._get_package_name(pkg_key, element)
			if pkg_name == package_name or pkg_key == package_name:
				return pkg_key

		return None

	def get_package_info(self, package_name: str) -> PackageInfo | None:
		"""
		Get detailed information about an installed package.

		Args:
			package_name: Package attribute name

		Returns:
			PackageInfo dict or None if not found
		"""
		loaded = self._load_manifest()
		if not loaded:
			return None

		for pkg_key, element in loaded["elements"].items():
			pkg_name = self._get_package_name(pkg_key, element)
			if pkg_name == package_name or pkg_key == package_name:
				return {
					"attrPath": element.get("attrPath", ""),
					"originalUrl": element.get("originalUrl", ""),
					"storePaths": element.get("storePaths", []),
					"url": element.get("url", ""),
				}

		return None

	def _extract_name_from_url(self, url: str) -> str:
		"""
		Extract package name from a flake URL.

		Examples:
			nixpkgs#firefox -> firefox
			github:NixOS/nixpkgs#vim -> vim
		"""
		if "#" in url:
			return url.split("#")[-1]
		return url.split("/")[-1]

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
			if "-" not in basename:
				return "unknown"

			parts = basename.split("-", 1)
			if len(parts) < 2:
				return "unknown"

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
					remainder = name_version[idx + len(package_name) :]
					# Remove leading dash if present
					if remainder.startswith("-"):
						remainder = remainder[1:]

					# The version is usually the first component
					if remainder:
						# Split on dash and take first part as version
						version = remainder.split("-")[0]
						if version:
							return version

			# Fallback: try to find version-like patterns (numbers and dots)
			parts = name_version.split("-")
			for part in reversed(parts):
				# Check if this part looks like a version
				if any(c.isdigit() for c in part) and ("." in part or part[0].isdigit()):
					return part

			return "unknown"

		except Exception:
			return "unknown"

	def get_package_files(self, package_name: str) -> list[str]:
		"""
		Get files installed by a package.

		Lists files from the package's store paths, focusing on
		desktop files and binaries that are useful for launching.

		Args:
			package_name: Package attribute name

		Returns:
			List of file paths
		"""
		info = self.get_package_info(package_name)
		if not info:
			return []

		files = []
		store_paths = info.get("storePaths", [])

		for store_path in store_paths:
			store_dir = Path(store_path)
			if not store_dir.exists():
				continue

			# List desktop files (important for GNOME Software launch button)
			apps_dir = store_dir / "share" / "applications"
			if apps_dir.exists():
				for desktop_file in apps_dir.glob("*.desktop"):
					files.append(str(desktop_file))

			# List binaries
			bin_dir = store_dir / "bin"
			if bin_dir.exists():
				for binary in bin_dir.iterdir():
					if binary.is_file():
						files.append(str(binary))

			# List icons (useful for app display)
			icons_dir = store_dir / "share" / "icons"
			if icons_dir.exists():
				for icon in icons_dir.rglob("*"):
					if icon.is_file():
						files.append(str(icon))

		return files

	def get_desktop_file(self, package_name: str) -> str | None:
		"""
		Get the primary desktop file for a package.

		Args:
			package_name: Package attribute name

		Returns:
			Path to desktop file or None
		"""
		info = self.get_package_info(package_name)
		if not info:
			return None

		store_paths = info.get("storePaths", [])

		for store_path in store_paths:
			apps_dir = Path(store_path) / "share" / "applications"
			if apps_dir.exists():
				# Look for a desktop file matching the package name first
				for desktop_file in apps_dir.glob("*.desktop"):
					# Prefer files that match the package name
					if package_name.lower() in desktop_file.name.lower():
						return str(desktop_file)

				# Fall back to first desktop file found
				for desktop_file in apps_dir.glob("*.desktop"):
					return str(desktop_file)

		return None

	def is_empty(self) -> bool:
		"""Check if the profile is empty or doesn't exist."""
		loaded = self._load_manifest()
		if not loaded:
			return True
		return len(loaded["elements"]) == 0
