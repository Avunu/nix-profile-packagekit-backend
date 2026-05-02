#!/usr/bin/python3
#
# Licensed under the GNU General Public License Version 2
#
# Nix search integration for PackageKit backend using diamondburned/nix-search

"""
Module for searching nixpkgs packages using a local nix-search index.

Uses diamondburned/nix-search with a pre-built Bluge full-text index for
instant offline results (~33ms). The index is built from the flake registry's
nixpkgs by a background systemd timer.

https://github.com/diamondburned/nix-search
"""

import json
import subprocess

# Default index path (system-wide, built by systemd timer)
DEFAULT_INDEX_PATH = "/var/cache/nix-search"


class NixSearch:
	"""
	Search nixpkgs using diamondburned/nix-search with a local index.

	The index is pre-built by a systemd timer from the flake registry's nixpkgs.
	Searches are fully offline and take ~33ms.
	"""

	def __init__(self, index_path: str = DEFAULT_INDEX_PATH):
		"""
		Initialize the nix search wrapper.

		Args:
			index_path: Path to the nix-search index directory
		"""
		self.index_path = index_path
		self._cache: dict[str, dict] = {}

	def search(self, terms: list[str], limit: int = 100) -> dict[str, dict]:
		"""
		Search for packages by name/description.

		Args:
			terms: Search terms
			limit: Maximum results to return

		Returns:
			Dictionary mapping package attribute names to metadata
		"""
		search_query = " ".join(terms)
		if not search_query:
			return {}

		packages = self._run_search(search_query)
		# Limit results
		results = {}
		for pkg in packages[:limit]:
			attr_name = self._extract_attr(pkg)
			if attr_name:
				results[attr_name] = self._parse_package(pkg)

		return results

	def search_by_name(self, name: str, limit: int = 20) -> dict[str, dict]:
		"""Search by package attribute name (exact match)."""
		packages = self._run_search(name, exact=True)

		results = {}
		for pkg in packages[:limit]:
			attr_name = self._extract_attr(pkg)
			if attr_name:
				results[attr_name] = self._parse_package(pkg)

		return results

	def _run_search(self, query: str, exact: bool = False) -> list[dict]:
		"""
		Run nix-search and return parsed JSON results.

		Args:
			query: Search query string
			exact: Whether to use exact matching

		Returns:
			List of raw package dicts from nix-search JSON output
		"""
		cmd = [
			"nix-search",
			"--index-path",
			self.index_path,
			"--json",
			"--no-color",
			"--no-pager",
		]

		if exact:
			cmd.append("--exact")

		cmd.append(query)

		try:
			result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

			if result.returncode != 0:
				return []

			# Output is a JSON array
			packages = json.loads(result.stdout)
			if isinstance(packages, list):
				return packages
			return []

		except subprocess.TimeoutExpired:
			return []
		except (json.JSONDecodeError, Exception):
			return []

	def _extract_attr(self, pkg: dict) -> str:
		"""
		Extract the package attribute name from nix-search output.

		The 'path' field is like "nixpkgs#firefox" — we want "firefox".
		Falls back to 'name' field.
		"""
		path = pkg.get("path", "")
		if "#" in path:
			return path.split("#", 1)[1]
		return pkg.get("name", "")

	def _normalize_version(self, version: str) -> str:
		"""
		Normalize a version string by stripping common wrapper suffixes.

		Nix packages often have wrapper suffixes like '-wrapped' in their metadata
		that don't appear in the actual installed version.

		Args:
			version: Version string (e.g., "25.8.2.2-wrapped", "1.0.0-unwrapped")

		Returns:
			Normalized version (e.g., "25.8.2.2", "1.0.0")
		"""
		if not version:
			return version

		wrapper_suffixes = ["-wrapped", "-unwrapped"]

		normalized = version
		for suffix in wrapper_suffixes:
			if normalized.endswith(suffix):
				normalized = normalized[: -len(suffix)]
				break

		return normalized

	def _parse_package(self, pkg: dict) -> dict:
		"""Parse nix-search JSON output into our internal format."""
		description = pkg.get("description", "")

		# Format license
		licenses = pkg.get("license", [])
		if licenses and isinstance(licenses, list):
			license_str = licenses[0]
		else:
			license_str = "unknown"

		# Get and normalize version
		raw_version = pkg.get("version", "unknown")
		normalized_version = self._normalize_version(raw_version)

		return {
			"pname": pkg.get("name", self._extract_attr(pkg)),
			"version": normalized_version,
			"description": description,
			"summary": description[:200] if description else "",
			"homepage": "",  # Not available in nix-search index
			"license": license_str,
			"mainProgram": pkg.get("mainProgram", ""),
		}

	def get_package_info(self, package_name: str) -> dict | None:
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
		results = self.search_by_name(package_name, limit=10)

		# Look for exact match
		if package_name in results:
			self._cache[package_name] = results[package_name]
			return results[package_name]

		# Try pname match
		for _name, info in results.items():
			if info.get("pname") == package_name:
				self._cache[package_name] = info
				return info

		return None

	def resolve_package(self, package_name: str) -> tuple[str, str] | None:
		"""
		Resolve a package name to its attribute path and version.

		Args:
			package_name: Package name to resolve

		Returns:
			Tuple of (attribute_path, version) or None
		"""
		info = self.get_package_info(package_name)
		if info:
			return (package_name, info.get("version", "unknown"))

		# Try general search
		results = self.search([package_name], limit=5)
		if package_name in results:
			return (package_name, results[package_name].get("version", "unknown"))

		# Check if any result is an exact pname match
		for name, info in results.items():
			if info.get("pname") == package_name:
				return (name, info.get("version", "unknown"))

		return None
