#!/usr/bin/python3
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
# Copyright (C) 2025 PackageKit Nix Backend Contributors

"""
PackageKit backend for Nix profile management (Python implementation).

This is a Python-based backend that focuses on user profile management via
`nix profile` commands, with integration of appdata streams.

Backend name: nix-profile
"""

import json
import os
import subprocess
import sys
import threading

from packagekit.backend import PackageKitBaseBackend, get_package_id, split_package_id
from packagekit.enums import (
	# Errors
	ERROR_INTERNAL_ERROR,
	ERROR_NOT_SUPPORTED,
	ERROR_PACKAGE_FAILED_TO_INSTALL,
	ERROR_PACKAGE_FAILED_TO_REMOVE,
	ERROR_PACKAGE_NOT_FOUND,
	# Groups
	GROUP_ACCESSORIES,
	GROUP_ADMIN_TOOLS,
	GROUP_EDUCATION,
	GROUP_GAMES,
	GROUP_GRAPHICS,
	GROUP_INTERNET,
	GROUP_MULTIMEDIA,
	GROUP_OFFICE,
	GROUP_PROGRAMMING,
	GROUP_SCIENCE,
	GROUP_SYSTEM,
	GROUP_UNKNOWN,
	# Info
	INFO_AVAILABLE,
	INFO_INSTALLED,
	INFO_NORMAL,
	INFO_REMOVING,
	INFO_UPDATING,
	# Misc
	RESTART_NONE,
	# Status
	STATUS_INFO,
	STATUS_INSTALL,
	STATUS_QUERY,
	STATUS_REFRESH_CACHE,
	STATUS_REMOVE,
	STATUS_UPDATE,
	UPDATE_STATE_STABLE,
)
from packagekit.package import PackagekitPackage

# Import helper modules
from nix_profile import NixProfile
from nix_search import NixSearch


class NixLogParser:
	"""
	Parser for nix's internal-json log format.
	Extracts progress information from nix commands.
	"""

	def __init__(self, callback):
		"""
		Initialize parser with a callback for progress updates.

		Args:
		    callback: Function to call with progress info: callback(percent, status_msg)
		"""
		self.callback = callback
		self.activity_stack = []

	def parse_line(self, line: str):
		"""Parse a single line of JSON log output."""
		try:
			data = json.loads(line)
			action = data.get("action")

			if action == "start":
				self._handle_start(data)
			elif action == "stop":
				self._handle_stop(data)
			elif action == "result":
				self._handle_result(data)
			elif action == "msg":
				self._handle_msg(data)

		except (json.JSONDecodeError, KeyError):
			# Not all lines are JSON, skip non-JSON output
			pass

	def _handle_start(self, data):
		"""Handle activity start."""
		activity_id = data.get("id")
		text = data.get("text", "")
		parent = data.get("parent")

		self.activity_stack.append({"id": activity_id, "text": text, "parent": parent})

		# Estimate progress based on activity depth
		progress = min(20 + len(self.activity_stack) * 10, 90)
		self.callback(progress, text)

	def _handle_stop(self, data):
		"""Handle activity stop."""
		activity_id = data.get("id")

		# Remove from stack
		self.activity_stack = [a for a in self.activity_stack if a["id"] != activity_id]

		# Update progress
		progress = min(20 + len(self.activity_stack) * 10, 95)
		self.callback(progress, "Processing...")

	def _handle_result(self, data):
		"""Handle result messages."""
		result_type = data.get("type")
		fields = data.get("fields", {})

		if result_type == "progress":
			done = fields.get("done", 0)
			total = fields.get("total", 1)
			if total > 0:
				percent = int((done / total) * 100)
				self.callback(percent, f"Progress: {done}/{total}")

	def _handle_msg(self, data):
		"""Handle log messages."""
		level = data.get("level")
		msg = data.get("msg", "")

		if level in ["error", "warn"]:
			# Don't update progress for errors/warnings, just pass message
			self.callback(None, msg)


class PackageKitNixProfileBackend(PackageKitBaseBackend, PackagekitPackage):
	"""
	PackageKit backend for Nix profile management.
	"""

	def __init__(self, args):
		PackageKitBaseBackend.__init__(self, args)

		# Initialize nix profile manager (resolves user from PackageKit UID)
		self.profile = NixProfile()

		# Store the profile path for nix commands
		self._profile_path = str(self.profile.profile_path)

		# Initialize nix search for package lookups
		self.nix_search = NixSearch()

		# Cache for package metadata
		self._metadata_cache = {}

		# Lock for thread-safe operations
		self._lock = threading.Lock()

	def _run_nix_command(
		self, args: list[str], parse_json: bool = True, use_profile: bool = True
	) -> tuple[int, str, str]:
		"""
		Run a nix command and optionally parse JSON output.

		Args:
		    args: Command arguments (without 'nix')
		    parse_json: Whether to use --log-format internal-json
		    use_profile: Whether to inject --profile flag for profile commands

		Returns:
		    Tuple of (returncode, stdout, stderr)
		"""
		cmd = ["nix", *args]

		# Inject --profile and --impure flags for profile operations to target the user's profile
		# This ensures we modify the requesting user's profile, not root's
		# --impure allows importing environment variables (e.g., NIXPKGS_ALLOW_UNFREE)
		# Command structure: nix profile <action> [--profile <path>] [--impure] <args>
		# e.g., nix profile install --profile /path/to/profile --impure nixpkgs#pkg
		if use_profile and len(args) >= 2 and args[0] == "profile":
			# Insert --profile and --impure after the action (install/remove/upgrade)
			# cmd is ["nix", "profile", "action", ...], so insert at index 3
			cmd.insert(3, "--profile")
			cmd.insert(4, self._profile_path)
			cmd.insert(5, "--impure")

		if parse_json and "--log-format" not in " ".join(args):
			cmd.extend(["--log-format", "internal-json"])

		# Build environment with NIXPKGS_ALLOW_* variables
		# This is critical for packages with unfree/insecure licenses
		env = os.environ.copy()
		# Ensure common allow flags are passed through
		for key in list(env.keys()):
			if key.startswith("NIXPKGS_ALLOW_"):
				# Keep these in the environment
				pass

		try:
			process = subprocess.Popen(
				cmd,
				stdout=subprocess.PIPE,
				stderr=subprocess.PIPE,
				universal_newlines=True,
				bufsize=1,
				env=env,
			)

			stdout_lines = []
			stderr_lines = []

			if parse_json:
				parser = NixLogParser(self._update_progress)

				# Read stderr (where nix logs go) line by line
				if process.stderr:
					for line in process.stderr:
						stderr_lines.append(line)
						parser.parse_line(line.strip())

			stdout, remaining_stderr = process.communicate()
			stdout_lines.append(stdout)
			stderr_lines.append(remaining_stderr)

			# Filter out JSON log lines from stderr to get clean error messages
			raw_stderr = "".join(stderr_lines)
			filtered_stderr = self._filter_nix_stderr(raw_stderr)

			return (process.returncode, "".join(stdout_lines), filtered_stderr)

		except FileNotFoundError:
			self.error(ERROR_INTERNAL_ERROR, "nix command not found. Is Nix installed?")
			return (1, "", "nix not found")
		except Exception as e:
			self.error(ERROR_INTERNAL_ERROR, f"Failed to run nix command: {e!s}")
			return (1, "", str(e))

	def _update_progress(self, percent: int | None, message: str):
		"""Update progress during nix operations."""
		if percent is not None:
			self.percentage(percent)
		if message:
			self.status(STATUS_INFO)

	def _filter_nix_stderr(self, stderr: str) -> str:
		"""
		Filter out JSON log lines from nix stderr output.

		Nix's internal-json log format outputs JSON objects to stderr.
		We want to filter these out and only keep actual error messages
		for display to the user.

		Args:
		    stderr: Raw stderr output from nix command

		Returns:
		    Filtered stderr with only human-readable error messages
		"""
		filtered_lines = []
		for line in stderr.splitlines():
			stripped = line.strip()
			# Skip JSON log lines (start with @nix or are JSON objects)
			if stripped.startswith("@nix ") or stripped.startswith('{"action"'):
				continue
			# Skip empty lines
			if not stripped:
				continue
			filtered_lines.append(line)

		return "\n".join(filtered_lines)

	def _pkg_to_package_id(self, pkg_name: str, version: str = "", arch: str = "noarch") -> str:
		"""
		Convert package information to PackageKit package ID.

		Format: name;version;arch;data
		For nix: name;version;noarch;nixpkgs
		"""
		return get_package_id(pkg_name, version or "unknown", arch, "nixpkgs")

	def _parse_package_id(self, package_id: str) -> list[str]:
		"""Parse a PackageKit package ID into [name, version, arch, data]."""
		return split_package_id(package_id)

	def _get_package_metadata(self, pkg_name: str) -> dict | None:
		"""
		Get package metadata from appdata cache.

		Args:
		    pkg_name: Package attribute name (e.g., 'firefox', 'python3')

		Returns:
		    Dictionary with package metadata or None
		"""
		if pkg_name in self._metadata_cache:
			return self._metadata_cache[pkg_name]

		metadata = self.nix_search.get_package_info(pkg_name)
		if metadata:
			self._metadata_cache[pkg_name] = metadata

		return metadata

	def _emit_package(self, pkg_name: str, version: str, info_type: str):
		"""
		Emit a package with metadata.

		Args:
		    pkg_name: Package attribute name
		    version: Package version
		    info_type: INFO_INSTALLED, INFO_AVAILABLE, etc.
		"""
		package_id = self._pkg_to_package_id(pkg_name, version)

		# Get metadata for summary
		metadata = self._get_package_metadata(pkg_name)
		summary = ""
		if metadata:
			summary = metadata.get("summary", metadata.get("description", ""))
			# Truncate long summaries
			if len(summary) > 100:
				summary = summary[:97] + "..."

		self.package(package_id, info_type, summary)

	# =========================================================================
	# PackageKit Backend Methods
	# =========================================================================

	def get_depends(self, filters, package_ids, recursive):
		"""
		Get package dependencies.
		Note: Nix profile doesn't expose dependency information easily.
		This is a no-op for now.
		"""
		self.error(ERROR_NOT_SUPPORTED, "Dependency information not available for nix profile")

	def get_details(self, package_ids):
		"""Get detailed information about packages."""
		self.status(STATUS_INFO)
		self.allow_cancel(True)

		for package_id in package_ids:
			pkg_name, _version, _arch, _data = self._parse_package_id(package_id)

			metadata = self._get_package_metadata(pkg_name)

			if metadata:
				summary = metadata.get("summary", "")
				description = metadata.get("description", summary)
				license_str = metadata.get("license", "unknown")
				homepage = metadata.get("homepage", "")

				# Map categories to groups
				categories = metadata.get("categories", [])
				group = self._map_category_to_group(categories)

				self.details(
					package_id,
					summary,
					license_str,
					group,
					description,
					homepage,
					0,  # size unknown for nix
				)
			else:
				# Fallback if no metadata
				self.details(
					package_id, "Nix package", "unknown", GROUP_UNKNOWN, f"Package {pkg_name}", "", 0
				)

	def _map_category_to_group(self, categories: list[str]) -> str:
		"""Map appdata categories to PackageKit groups."""
		category_map = {
			"AudioVideo": GROUP_MULTIMEDIA,
			"Audio": GROUP_MULTIMEDIA,
			"Video": GROUP_MULTIMEDIA,
			"Development": GROUP_PROGRAMMING,
			"Education": GROUP_EDUCATION,
			"Game": GROUP_GAMES,
			"Graphics": GROUP_GRAPHICS,
			"Network": GROUP_INTERNET,
			"Office": GROUP_OFFICE,
			"Science": GROUP_SCIENCE,
			"Settings": GROUP_ADMIN_TOOLS,
			"System": GROUP_SYSTEM,
			"Utility": GROUP_ACCESSORIES,
		}

		for category in categories:
			if category in category_map:
				return category_map[category]

		return GROUP_UNKNOWN

	def get_files(self, package_ids):
		"""
		Get files contained in packages.
		Lists files from the package's store paths.
		"""
		self.status(STATUS_INFO)

		for package_id in package_ids:
			pkg_name, _version, _arch, _data = self._parse_package_id(package_id)
			files = self.profile.get_package_files(pkg_name)
			self.files(package_id, files)

	def get_update_detail(self, package_ids):
		"""Get details about available updates."""
		self.status(STATUS_INFO)

		for package_id in package_ids:
			pkg_name, old_version, _arch, _data = self._parse_package_id(package_id)

			# Get latest version from appdata
			metadata = self._get_package_metadata(pkg_name)
			new_version = metadata.get("version", "unknown") if metadata else "unknown"

			self.update_detail(
				package_id,
				"",  # updates
				"",  # obsoletes
				"",  # vendor_url
				"",  # bugzilla_url
				"",  # cve_url
				RESTART_NONE,
				f"Update {pkg_name} from {old_version} to {new_version}",
				"",  # changelog
				UPDATE_STATE_STABLE,
				"",  # issued
				"",  # updated
			)

	def get_updates(self, filters):
		"""Get available updates for installed packages."""
		self.status(STATUS_INFO)
		self.percentage(0)
		self.allow_cancel(True)

		# Get installed packages
		installed = self.profile.get_installed_packages()

		if not installed:
			self.percentage(100)
			return

		# Check each package for updates
		total = len(installed)
		for i, (pkg_name, current_version) in enumerate(installed.items()):
			# Get latest version from appdata
			metadata = self._get_package_metadata(pkg_name)

			if metadata:
				latest_version = metadata.get("version", "")

				# Simple version comparison (nix versions can be complex)
				if latest_version and latest_version != current_version:
					package_id = self._pkg_to_package_id(pkg_name, latest_version)
					summary = metadata.get("summary", "")
					self.package(package_id, INFO_NORMAL, summary)

			# Update progress
			percent = int((i + 1) / total * 100)
			self.percentage(percent)

	def install_files(self, only_trusted, files):
		"""Install local .drv or .nix files."""
		self.error(
			ERROR_NOT_SUPPORTED, "Installing local files not supported. Use 'nix profile install' directly."
		)

	def install_packages(self, transaction_flags, package_ids):
		"""Install packages to the user's nix profile."""
		self.status(STATUS_INSTALL)
		self.percentage(0)
		self.allow_cancel(False)

		for package_id in package_ids:
			pkg_name, version, _arch, _data = self._parse_package_id(package_id)

			self.status(STATUS_INSTALL)
			self.percentage(10)

			# Construct the installable (nixpkgs#package)
			installable = f"nixpkgs#{pkg_name}"

			# Run nix profile install
			rc, _stdout, stderr = self._run_nix_command(["profile", "install", installable])

			if rc == 0:
				self.percentage(100)
				# Re-emit the package as installed
				self._emit_package(pkg_name, version, INFO_INSTALLED)
			else:
				self.error(ERROR_PACKAGE_FAILED_TO_INSTALL, f"Failed to install {pkg_name}: {stderr}")

	def refresh_cache(self, force):
		"""Refresh the package cache and appdata."""
		self.status(STATUS_REFRESH_CACHE)
		self.percentage(0)
		self.allow_cancel(True)

		# Update nix flake registry
		self.percentage(10)
		_rc, _stdout, _stderr = self._run_nix_command(["registry", "pin", "nixpkgs"], parse_json=False)

		# Note: registry pin failure is non-fatal, we continue anyway

		# nix search always uses fresh data, no appdata cache needed
		self.percentage(100)

	def remove_packages(self, transaction_flags, package_ids, allowdeps, autoremove):
		"""Remove packages from the user's nix profile."""
		self.status(STATUS_REMOVE)
		self.percentage(0)
		self.allow_cancel(False)

		for package_id in package_ids:
			pkg_name, version, _arch, _data = self._parse_package_id(package_id)

			self.status(STATUS_REMOVE)
			self.percentage(10)

			# Find the profile element index for this package
			element_index = self.profile.find_package_index(pkg_name)

			if element_index is None:
				self.error(ERROR_PACKAGE_NOT_FOUND, f"Package {pkg_name} not found in profile")
				continue

			# Run nix profile remove
			rc, _stdout, stderr = self._run_nix_command(["profile", "remove", str(element_index)])

			if rc == 0:
				self.percentage(100)
				self._emit_package(pkg_name, version, INFO_REMOVING)
			else:
				self.error(ERROR_PACKAGE_FAILED_TO_REMOVE, f"Failed to remove {pkg_name}: {stderr}")

	def resolve(self, filters, packages):
		"""Resolve package names to package IDs."""
		self.status(STATUS_QUERY)
		self.allow_cancel(True)

		# Check if package is installed
		installed = self.profile.get_installed_packages()

		for package_name in packages:
			if package_name in installed:
				# Package is installed
				version = installed[package_name]
				self._emit_package(package_name, version, INFO_INSTALLED)
			else:
				# Check if package exists in nixpkgs via appdata
				metadata = self._get_package_metadata(package_name)
				if metadata:
					version = metadata.get("version", "unknown")
					self._emit_package(package_name, version, INFO_AVAILABLE)

	def search_details(self, filters, values):
		"""Search package descriptions."""
		self.status(STATUS_QUERY)
		self.percentage(0)
		self.allow_cancel(True)

		search_terms = [v.lower() for v in values]
		results = self.nix_search.search(search_terms)

		installed = self.profile.get_installed_packages()

		total = len(results)
		for i, (pkg_name, metadata) in enumerate(results.items()):
			version = metadata.get("version", "unknown")

			if pkg_name in installed:
				info_type = INFO_INSTALLED
				version = installed[pkg_name]
			else:
				info_type = INFO_AVAILABLE

			# Use metadata from search results directly instead of re-fetching
			package_id = self._pkg_to_package_id(pkg_name, version)
			summary = metadata.get("summary", metadata.get("description", ""))
			if len(summary) > 100:
				summary = summary[:97] + "..."
			self.package(package_id, info_type, summary)

			percent = int((i + 1) / total * 100) if total > 0 else 100
			self.percentage(percent)

	def search_file(self, filters, values):
		"""
		Search for packages containing files.
		Searches installed packages for matching file names.
		"""
		self.status(STATUS_QUERY)
		self.percentage(0)
		self.allow_cancel(True)

		search_terms = [v.lower() for v in values]
		installed = self.profile.get_installed_packages()

		total = len(installed)
		for i, (pkg_name, version) in enumerate(installed.items()):
			files = self.profile.get_package_files(pkg_name)

			# Check if any file matches search terms
			for filepath in files:
				filename = filepath.lower()
				if any(term in filename for term in search_terms):
					self._emit_package(pkg_name, version, INFO_INSTALLED)
					break  # Only emit package once

			percent = int((i + 1) / total * 100) if total > 0 else 100
			self.percentage(percent)

	def search_group(self, filters, values):
		"""Search for packages by group."""
		self.status(STATUS_QUERY)
		self.percentage(0)
		self.allow_cancel(True)

		# Map PackageKit groups to appdata categories
		group_to_category = {
			GROUP_MULTIMEDIA: ["AudioVideo", "Audio", "Video"],
			GROUP_PROGRAMMING: ["Development"],
			GROUP_EDUCATION: ["Education"],
			GROUP_GAMES: ["Game"],
			GROUP_GRAPHICS: ["Graphics"],
			GROUP_INTERNET: ["Network"],
			GROUP_OFFICE: ["Office"],
			GROUP_SCIENCE: ["Science"],
			GROUP_ADMIN_TOOLS: ["Settings", "System"],
			GROUP_ACCESSORIES: ["Utility"],
		}

		categories = []
		for group in values:
			if group in group_to_category:
				categories.extend(group_to_category[group])

		if not categories:
			return

		# nix search doesn't support categories natively, so search by category names as terms
		# This is a best-effort approximation
		results = self.nix_search.search(categories)
		installed = self.profile.get_installed_packages()

		total = len(results)
		for i, (pkg_name, metadata) in enumerate(results.items()):
			version = metadata.get("version", "unknown")

			if pkg_name in installed:
				info_type = INFO_INSTALLED
				version = installed[pkg_name]
			else:
				info_type = INFO_AVAILABLE

			# Use metadata from search results directly instead of re-fetching
			package_id = self._pkg_to_package_id(pkg_name, version)
			summary = metadata.get("summary", metadata.get("description", ""))
			if len(summary) > 100:
				summary = summary[:97] + "..."
			self.package(package_id, info_type, summary)

			percent = int((i + 1) / total * 100) if total > 0 else 100
			self.percentage(percent)

	def search_name(self, filters, values):
		"""Search package names."""
		self.status(STATUS_QUERY)
		self.percentage(0)
		self.allow_cancel(True)

		search_terms = [v.lower() for v in values]
		results = self.nix_search.search(search_terms)

		installed = self.profile.get_installed_packages()

		total = len(results)
		for i, (pkg_name, metadata) in enumerate(results.items()):
			version = metadata.get("version", "unknown")

			if pkg_name in installed:
				info_type = INFO_INSTALLED
				version = installed[pkg_name]
			else:
				info_type = INFO_AVAILABLE

			# Use metadata from search results directly instead of re-fetching
			package_id = self._pkg_to_package_id(pkg_name, version)
			summary = metadata.get("summary", metadata.get("description", ""))
			if len(summary) > 100:
				summary = summary[:97] + "..."
			self.package(package_id, info_type, summary)

			percent = int((i + 1) / total * 100) if total > 0 else 100
			self.percentage(percent)

	def update_packages(self, transaction_flags, package_ids):
		"""Update packages in the user's nix profile."""
		self.status(STATUS_UPDATE)
		self.percentage(0)
		self.allow_cancel(False)

		for package_id in package_ids:
			pkg_name, version, _arch, _data = self._parse_package_id(package_id)

			self.status(STATUS_UPDATE)
			self.percentage(10)

			# Find the profile element index
			element_index = self.profile.find_package_index(pkg_name)

			if element_index is None:
				self.error(ERROR_PACKAGE_NOT_FOUND, f"Package {pkg_name} not found in profile")
				continue

			# Run nix profile upgrade
			rc, _stdout, stderr = self._run_nix_command(["profile", "upgrade", str(element_index)])

			if rc == 0:
				self.percentage(100)
				# Get new version
				installed = self.profile.get_installed_packages()
				new_version = installed.get(pkg_name, version)
				self._emit_package(pkg_name, new_version, INFO_UPDATING)
			else:
				self.error(ERROR_PACKAGE_FAILED_TO_INSTALL, f"Failed to update {pkg_name}: {stderr}")

	def update_system(self, transaction_flags):
		"""Update all packages in the user's nix profile."""
		self.status(STATUS_UPDATE)
		self.percentage(10)
		self.allow_cancel(False)

		# Run nix profile upgrade (without index = upgrade all)
		rc, _stdout, stderr = self._run_nix_command(["profile", "upgrade", ".*"])

		if rc == 0:
			self.percentage(100)
		else:
			self.error(ERROR_PACKAGE_FAILED_TO_INSTALL, f"Failed to upgrade profile: {stderr}")

	def get_packages(self, filters):
		"""Get all packages (installed and available)."""
		self.status(STATUS_QUERY)
		self.percentage(0)
		self.allow_cancel(True)

		# Get installed packages
		installed = self.profile.get_installed_packages()

		# Check filters
		show_installed = "installed" not in filters or "installed" in filters

		if show_installed:
			for pkg_name, version in installed.items():
				self._emit_package(pkg_name, version, INFO_INSTALLED)

		# Getting all available packages could be very slow
		# For now, just return installed packages
		# A full implementation would query the appdata database

		self.percentage(100)


def main():
	backend = PackageKitNixProfileBackend("")
	backend.dispatcher(sys.argv[1:])


if __name__ == "__main__":
	main()
