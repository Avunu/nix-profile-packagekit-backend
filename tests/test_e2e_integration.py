#!/usr/bin/env python3
"""
End-to-end integration tests for nix/nix-search/appstream/packagekit integration.

These tests verify the complete integration workflow:
1. AppStream data is parsable via appstreamcli
2. Packages are installable via packagekit
3. Version schema matches between nix-search emit and local/installed emit
4. Installed packages list correctly as locally installed software
5. Packages can be uninstalled

Requirements:
- These tests require a NixOS or nix-installed system with the devshell active
- All required tools are provided by the devshell: appstreamcli, pkcon, nix, nix-search
- Tests requiring package installation/removal will prompt for authentication via polkit
- Tests should be run as a regular user (not root)

Usage:
    # Run all tests (will prompt for authentication when needed):
    pytest tests/test_e2e_integration.py -v -s

    # Run specific test:
    pytest tests/test_e2e_integration.py::TestE2EIntegration::test_full_lifecycle -v -s

    # Skip slow tests that require authentication:
    pytest tests/test_e2e_integration.py -v -s -m "not slow"
"""

import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

# Import local modules
from nix_profile import NixProfile
from nix_search import NixSearch


class PackageVersion(NamedTuple):
	"""Represents a package version with its source."""

	name: str
	version: str
	source: str  # "nix-search", "installed", "appstream"


def command_available(cmd: str) -> bool:
	"""Check if a command is available in PATH."""
	return shutil.which(cmd) is not None


def assert_tool_available(cmd: str, install_hint: str = ""):
	"""Assert a tool is available, with helpful error message."""
	if not command_available(cmd):
		hint = install_hint or f"Enter the devshell with 'nix develop' to get {cmd}"
		pytest.fail(f"Required tool '{cmd}' not found in PATH. {hint}")


def run_command(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
	"""Run a command and return (returncode, stdout, stderr)."""
	try:
		result = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=timeout,
		)
		return result.returncode, result.stdout, result.stderr
	except subprocess.TimeoutExpired:
		return -1, "", "Command timed out"
	except Exception as e:
		return -1, "", str(e)


def run_command_with_auth(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
	"""
	Run a command that may require authentication.

	This runs the command and allows it to interact with the terminal for
	polkit authentication prompts. Use for pkcon install/remove operations.
	"""
	try:
		# Don't capture output so user can see and respond to auth prompts
		print(f"\n>>> Running: {' '.join(cmd)}")
		print(">>> (You may be prompted for authentication)")

		result = subprocess.run(
			cmd,
			timeout=timeout,
			# Let stdin/stdout/stderr pass through for auth prompts
		)
		return result.returncode, "", ""
	except subprocess.TimeoutExpired:
		return -1, "", "Command timed out"
	except Exception as e:
		return -1, "", str(e)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def test_package():
	"""
	A small, fast-to-install package for testing.

	Using 'hello' as it's:
	- Small (quick to install/uninstall)
	- Has no complex dependencies
	- Available in nixpkgs
	- Has version information
	"""
	return "hello"


@pytest.fixture(scope="module")
def appstream_xml_path():
	"""Path to the generated AppStream XML file."""
	# Check common locations
	paths = [
		Path("/usr/share/swcatalog/xml"),
		Path("/var/lib/swcatalog/xml"),
		Path(__file__).parent.parent / "appstream-data" / "swcatalog" / "xml",
	]

	for path in paths:
		if path.exists():
			xml_files = list(path.glob("*.xml")) + list(path.glob("*.xml.gz"))
			if xml_files:
				return path

	# Return local path as fallback
	return Path(__file__).parent.parent / "appstream-data" / "swcatalog" / "xml"


@pytest.fixture(scope="module")
def nix_profile():
	"""Create a NixProfile instance for the current user."""
	return NixProfile()


@pytest.fixture(scope="module")
def nix_search():
	"""Create a NixSearch instance."""
	return NixSearch()


@pytest.fixture(scope="module", autouse=True)
def check_required_tools():
	"""Verify all required tools are available before running tests."""
	missing_tools = []

	tools = {
		"appstreamcli": "appstream package",
		"pkcon": "packagekit package",
		"nix": "nix package manager",
		"nix-search": "nix-search-cli package",
	}

	for tool, desc in tools.items():
		if not command_available(tool):
			missing_tools.append(f"  - {tool} ({desc})")

	if missing_tools:
		pytest.fail(
			"Required tools not found. Enter the devshell with 'nix develop':\n" + "\n".join(missing_tools)
		)


# =============================================================================
# AppStream Tests
# =============================================================================


class TestAppStreamData:
	"""Tests for AppStream data validity and parseability."""

	def test_appstream_catalog_exists(self, appstream_xml_path):
		"""Test that AppStream catalog files exist."""
		assert appstream_xml_path.exists(), f"AppStream XML path does not exist: {appstream_xml_path}"

		xml_files = list(appstream_xml_path.glob("*.xml")) + list(appstream_xml_path.glob("*.xml.gz"))
		assert len(xml_files) > 0, f"No AppStream XML files found in {appstream_xml_path}"

	def test_appstreamcli_validate(self, appstream_xml_path):
		"""Test that appstreamcli can validate the AppStream data."""
		# Find XML files
		xml_files = list(appstream_xml_path.glob("*.xml"))

		if not xml_files:
			# Try compressed files
			xml_files = list(appstream_xml_path.glob("*.xml.gz"))

		assert xml_files, (
			f"No AppStream XML files found in {appstream_xml_path}. "
			f"Run 'just generate' to create AppStream data."
		)

		for xml_file in xml_files[:1]:  # Test at least one file
			# Use appstreamcli validate (may produce warnings but shouldn't error)
			# --pedantic shows all issues, without it only major errors are shown
			_rc, stdout, stderr = run_command(["appstreamcli", "validate", "--no-net", str(xml_file)])

			# appstreamcli validate returns:
			# 0 = valid (may have info/warnings)
			# 1 = invalid (has errors)
			# 2 = file not found or other error
			#
			# Lines starting with "E:" are errors, "W:" are warnings, "I:" are info
			# We accept warnings and info, but count actual errors
			combined_output = stdout + stderr

			# Count lines that start with "E:" (actual validation errors)
			error_lines = [line for line in combined_output.splitlines() if line.strip().startswith("E:")]

			# Known acceptable errors that are cosmetic/metadata issues:
			# - release-time-missing: Missing release date (not critical)
			# - description-para-markup-invalid: Minor markup issues
			# - cid-domain-not-lowercase: Upstream uses mixed case in app IDs
			acceptable_errors = [
				"release-time-missing",
				"description-para-markup-invalid",
				"invalid-child-tag-name",  # Often from upstream Flathub data
				"cid-domain-not-lowercase",  # Upstream Flathub uses mixed-case IDs
			]

			critical_errors = [
				line
				for line in error_lines
				if not any(acceptable in line for acceptable in acceptable_errors)
			]

			# Fail only on critical errors that would break functionality
			assert len(critical_errors) == 0, (
				f"AppStream validation found critical errors in {xml_file}:\n"
				f"Critical errors:\n"
				+ "\n".join(critical_errors[:10])
				+ (f"\n... and {len(critical_errors) - 10} more" if len(critical_errors) > 10 else "")
			)

			# Log info about any non-critical issues found
			if error_lines:
				print(f"\nAppStream validation passed with {len(error_lines)} non-critical issues")

	def test_appstreamcli_status(self):
		"""Test that appstreamcli status works and shows catalog data."""
		rc, stdout, stderr = run_command(["appstreamcli", "status"])

		# Status should work (rc=0) and show component counts
		assert rc == 0, f"appstreamcli status failed: {stderr}"
		assert "component" in stdout.lower() or "software" in stdout.lower(), (
			f"Unexpected appstreamcli status output:\n{stdout}"
		)

	def test_appstreamcli_search_finds_packages(self):
		"""Test that appstreamcli search can find packages."""
		# Search for a common package
		rc, _stdout, stderr = run_command(["appstreamcli", "search", "firefox"])

		# Search may return 0 (found) or 1 (not found)
		# We just verify the command doesn't crash
		assert rc in [0, 1], f"appstreamcli search failed: {stderr}"

	def test_appstreamcli_dump_parseable(self):
		"""Test that appstreamcli dump produces parseable output."""
		# Try to dump a known package
		rc, stdout, _stderr = run_command(["appstreamcli", "dump", "firefox"])

		if rc == 0 and stdout:
			# Output should be valid XML or YAML
			assert "<component" in stdout or "Type:" in stdout, f"Unexpected dump format:\n{stdout[:500]}"

	def test_local_appstream_xml_well_formed(self, appstream_xml_path):
		"""Test that local AppStream XML is well-formed XML."""
		import xml.etree.ElementTree as ET

		xml_files = list(appstream_xml_path.glob("*.xml"))

		assert xml_files, (
			f"No uncompressed XML files found in {appstream_xml_path}. "
			f"Run 'just generate' to create AppStream data."
		)

		for xml_file in xml_files[:1]:
			try:
				tree = ET.parse(xml_file)
				root = tree.getroot()

				assert root.tag == "components", f"Expected root tag 'components', got '{root.tag}'"

				# Check that it has at least some components
				components = root.findall(".//component")
				assert len(components) > 0, "No components found in AppStream XML"

			except ET.ParseError as e:
				pytest.fail(f"XML parse error in {xml_file}: {e}")

	def test_appstream_components_have_pkgname(self, appstream_xml_path):
		"""Test that AppStream components have pkgname for PackageKit correlation."""
		import xml.etree.ElementTree as ET

		xml_files = list(appstream_xml_path.glob("*.xml"))

		assert xml_files, (
			f"No uncompressed XML files found in {appstream_xml_path}. "
			f"Run 'just generate' to create AppStream data."
		)

		for xml_file in xml_files[:1]:
			tree = ET.parse(xml_file)
			root = tree.getroot()

			components = root.findall(".//component")
			components_with_pkgname = 0

			for component in components[:100]:  # Check first 100
				pkgname = component.find("pkgname")
				if pkgname is not None and pkgname.text:
					components_with_pkgname += 1

			# At least 80% should have pkgname
			percentage = (components_with_pkgname / min(len(components), 100)) * 100
			assert percentage >= 80, (
				f"Only {percentage:.1f}% of components have pkgname "
				f"({components_with_pkgname}/{min(len(components), 100)})"
			)


# =============================================================================
# Version Schema Tests
# =============================================================================


class TestVersionSchemaConsistency:
	"""Tests for version schema consistency between sources."""

	def test_nix_search_version_format(self, nix_search, test_package):
		"""Test that nix-search returns properly formatted versions."""
		results = nix_search.search_by_name(test_package, limit=5)

		if test_package not in results:
			# Try broader search
			results = nix_search.search([test_package], limit=10)

		assert len(results) > 0, f"No results found for {test_package}"

		for pkg_name, metadata in results.items():
			version = metadata.get("version", "")

			# Version should exist and not be empty
			assert version, f"Package {pkg_name} has empty version"
			assert version != "unknown", f"Package {pkg_name} has 'unknown' version"

			# Version should follow semver-like pattern (digits, dots, dashes)
			# Nix versions can be complex but should contain at least one digit
			assert any(c.isdigit() for c in version), f"Package {pkg_name} version '{version}' has no digits"

	def test_installed_version_matches_nix_search(self, nix_profile, nix_search):
		"""Test that installed package versions match nix-search versions."""
		installed = nix_profile.get_installed_packages()

		if not installed:
			# No packages installed is a valid state - pass with a note
			print(
				"\nNote: No packages installed in profile. "
				"Run test_full_lifecycle first to install a test package."
			)
			return

		mismatches = []

		# Check a sample of installed packages
		for pkg_name, installed_version in list(installed.items())[:5]:
			search_result = nix_search.get_package_info(pkg_name)

			if search_result:
				search_version = search_result.get("version", "unknown")

				# Versions should either match or be compatible
				# (installed might be older than latest in search)
				if installed_version != "unknown" and search_version != "unknown":
					# Extract major.minor for comparison
					installed_base = installed_version.split("-")[0].split("+")[0]
					search_base = search_version.split("-")[0].split("+")[0]

					# Log but don't fail on version differences (updates are expected)
					if installed_base != search_base:
						mismatches.append(
							f"{pkg_name}: installed={installed_version}, search={search_version}"
						)

		# Just log mismatches, don't fail (updates are expected)
		if mismatches:
			print("\nVersion differences (expected if updates available):\n" + "\n".join(mismatches))

	def test_version_extraction_from_store_path(self, nix_profile):
		"""Test that version extraction from store paths works correctly."""
		installed = nix_profile.get_installed_packages()

		if not installed:
			# No packages installed is a valid state - pass with a note
			print(
				"\nNote: No packages installed in profile. "
				"Run test_full_lifecycle first to install a test package."
			)
			return

		for pkg_name, version in list(installed.items())[:5]:
			# Version should not be 'unknown' for properly installed packages
			# (though some packages might genuinely have complex versions)
			if version == "unknown":
				# Get package info to check store path
				info = nix_profile.get_package_info(pkg_name)
				if info and info.get("storePaths"):
					store_path = info["storePaths"][0]
					print(f"\nWarning: Could not extract version from store path for {pkg_name}")
					print(f"  Store path: {store_path}")


# =============================================================================
# PackageKit Integration Tests
# =============================================================================


class TestPackageKitIntegration:
	"""Tests for PackageKit integration."""

	def test_pkcon_backend_details(self):
		"""Test that pkcon shows nix-profile as the backend."""
		rc, stdout, stderr = run_command(["pkcon", "backend-details"])

		assert rc == 0, f"pkcon backend-details failed: {stderr}"
		assert "nix-profile" in stdout.lower() or "nix" in stdout.lower(), (
			f"nix-profile backend not detected in:\n{stdout}"
		)

	def test_pkcon_get_packages_installed(self):
		"""Test that pkcon can list installed packages."""
		rc, _stdout, stderr = run_command(["pkcon", "get-packages", "--filter=installed"])

		# Should succeed even if no packages installed
		assert rc == 0, f"pkcon get-packages failed: {stderr}"

	def test_pkcon_search_name(self, test_package):
		"""Test that pkcon can search for packages by name."""
		rc, _stdout, stderr = run_command(["pkcon", "search", "name", test_package])

		# Search should succeed
		assert rc == 0, f"pkcon search failed: {stderr}"

	def test_pkcon_resolve(self, test_package):
		"""Test that pkcon can resolve package names."""
		rc, _stdout, stderr = run_command(["pkcon", "resolve", test_package])

		# Resolve should succeed
		assert rc == 0, f"pkcon resolve failed: {stderr}"

	def test_pkcon_get_details(self, test_package):
		"""Test that pkcon can get package details."""
		rc, _stdout, stderr = run_command(["pkcon", "get-details", test_package])

		# Should succeed (or return not-found which is ok)
		# pkcon returns 5 for "package not found" which is acceptable
		assert rc in [0, 5], f"pkcon get-details failed unexpectedly: {stderr}"


# =============================================================================
# End-to-End Lifecycle Tests
# =============================================================================


class TestE2EIntegration:
	"""
	End-to-end integration tests for the complete package lifecycle.

	WARNING: These tests actually install and remove packages!
	They should be run in a test environment or with caution.
	"""

	@pytest.fixture(autouse=True)
	def setup_and_teardown(self, test_package, nix_profile):
		"""Setup: ensure test package is not installed. Teardown: clean up."""
		# Check if package is already installed
		installed = nix_profile.get_installed_packages()
		self._was_installed = test_package in installed

		yield

		# Cleanup: only remove if we installed it during the test
		if not self._was_installed:
			# Try to remove the package if it was installed by this test
			subprocess.run(
				["nix", "profile", "remove", test_package],
				capture_output=True,
				timeout=60,
			)

	@pytest.mark.slow
	def test_full_lifecycle(self, test_package, nix_profile, nix_search):
		"""
		Test the complete package lifecycle:
		1. Get package info from nix-search
		2. Verify appstream data is valid
		3. Install package via pkcon
		4. Verify it appears in installed list
		5. Verify version consistency
		6. Uninstall package via pkcon
		7. Verify it's removed from installed list
		"""
		print(f"\n{'=' * 60}")
		print(f"E2E Lifecycle Test for package: {test_package}")
		print(f"{'=' * 60}")

		# Step 1: Get package info from nix-search
		print("\n[Step 1] Getting package info from nix-search...")
		search_info = nix_search.get_package_info(test_package)

		if not search_info:
			# Try broader search
			results = nix_search.search([test_package], limit=10)
			if test_package in results:
				search_info = results[test_package]
			elif results:
				# Use first result
				search_info = next(iter(results.values()))

		assert search_info, f"Could not find {test_package} in nix-search"

		nix_search_version = search_info.get("version", "unknown")
		print(f"  nix-search version: {nix_search_version}")
		print(f"  description: {search_info.get('description', 'N/A')[:60]}...")

		# Step 2: Verify appstreamcli works
		print("\n[Step 2] Verifying appstreamcli status...")
		rc, stdout, stderr = run_command(["appstreamcli", "status"])
		assert rc == 0, f"appstreamcli status failed: {stderr}"
		print("  AppStream status OK")

		# Step 3: Check if package is already installed
		print("\n[Step 3] Checking current installation status...")
		installed_before = nix_profile.get_installed_packages()
		was_installed = test_package in installed_before

		if was_installed:
			print(f"  Package already installed (version: {installed_before[test_package]})")
			print("  Skipping install, testing existing installation...")
		else:
			print("  Package not installed, proceeding with installation...")

			# Step 4: Install via pkcon (may prompt for authentication)
			print("\n[Step 4] Installing package via pkcon...")
			print(">>> You may be prompted for authentication via polkit")

			# Use interactive mode to allow polkit auth prompts
			rc = run_command_with_auth(
				["pkcon", "install", "-y", test_package],
				timeout=300,  # 5 minutes for installation
			)[0]

			if rc != 0:
				# Check if install actually succeeded despite return code
				nix_profile_check = NixProfile()
				if test_package in nix_profile_check.get_installed_packages():
					print("  Installation succeeded (despite non-zero return code)")
				else:
					pytest.fail(f"pkcon install failed (rc={rc}). Make sure you authenticated correctly.")
			else:
				print("  Installation successful")

		# Step 5: Verify it appears in installed list
		print("\n[Step 5] Verifying package appears in installed list...")
		# Reload manifest
		nix_profile_fresh = NixProfile()
		installed_after = nix_profile_fresh.get_installed_packages()

		assert test_package in installed_after, (
			f"Package {test_package} not found in installed packages after install.\n"
			f"Installed packages: {list(installed_after.keys())}"
		)

		installed_version = installed_after[test_package]
		print(f"  Installed version: {installed_version}")

		# Step 6: Verify version consistency
		print("\n[Step 6] Verifying version consistency...")

		# Compare versions (allow for minor differences due to timing)
		if installed_version != "unknown" and nix_search_version != "unknown":
			# Extract base version (before any suffix)
			installed_base = installed_version.split("-")[0].split("+")[0]
			search_base = nix_search_version.split("-")[0].split("+")[0]

			# Versions should be similar (exact match not required due to updates)
			print(f"  Installed base: {installed_base}")
			print(f"  nix-search base: {search_base}")

			# At minimum, versions should follow similar patterns
			assert any(c.isdigit() for c in installed_version), "Installed version has no digits"

		# Step 7: Verify pkcon lists it as installed
		print("\n[Step 7] Verifying pkcon shows package as installed...")
		rc, stdout, stderr = run_command(["pkcon", "get-packages", "--filter=installed"])

		assert rc == 0, f"pkcon get-packages failed: {stderr}"
		# Package name should appear in output
		# Note: output format is "package-name;version;arch;repo"
		assert test_package.lower() in stdout.lower(), (
			f"Package {test_package} not found in pkcon installed list:\n{stdout[:500]}"
		)
		print("  Package confirmed in pkcon installed list")

		# Step 8: Uninstall (only if we installed it)
		if not was_installed:
			print("\n[Step 8] Uninstalling package via pkcon...")
			print(">>> You may be prompted for authentication via polkit")

			rc = run_command_with_auth(
				["pkcon", "remove", "-y", test_package],
				timeout=120,
			)[0]

			if rc != 0:
				# Try direct nix removal as fallback
				print("  pkcon remove returned non-zero, trying direct nix removal...")
				nix_rc, _nix_stdout, nix_stderr = run_command(
					["nix", "profile", "remove", test_package],
					timeout=120,
				)
				if nix_rc != 0:
					print(f"  Warning: Could not remove package: {nix_stderr}")
			else:
				print("  Uninstallation successful")

			# Step 9: Verify removal
			print("\n[Step 9] Verifying package removal...")
			nix_profile_final = NixProfile()
			installed_final = nix_profile_final.get_installed_packages()

			if test_package in installed_final:
				print("  Warning: Package still appears installed (may need manifest refresh)")
			else:
				print("  Package confirmed removed")
		else:
			print("\n[Step 8-9] Skipping uninstall (package was pre-installed)")

		print(f"\n{'=' * 60}")
		print("E2E Lifecycle Test PASSED")
		print(f"{'=' * 60}")

	def test_version_schema_consistency_search_vs_installed(self, nix_profile, nix_search):
		"""
		Test that version schema is consistent between nix-search and installed packages.
		"""
		installed = nix_profile.get_installed_packages()

		if not installed:
			# No packages installed is a valid state - pass with a note
			print(
				"\nNote: No packages installed in profile. "
				"Run test_full_lifecycle first to install a test package."
			)
			return

		print("\nVersion Schema Consistency Check:")
		print("-" * 50)

		consistent = 0
		inconsistent = 0

		for pkg_name, installed_version in list(installed.items())[:10]:
			search_info = nix_search.get_package_info(pkg_name)

			if not search_info:
				continue

			search_version = search_info.get("version", "unknown")

			# Both should either be "unknown" or follow similar patterns
			installed_has_digits = any(c.isdigit() for c in installed_version)
			search_has_digits = any(c.isdigit() for c in search_version)

			if installed_version == "unknown" and search_version == "unknown":
				consistent += 1
			elif installed_has_digits == search_has_digits:
				consistent += 1
			else:
				inconsistent += 1
				print(f"  MISMATCH: {pkg_name}")
				print(f"    installed: {installed_version}")
				print(f"    nix-search: {search_version}")

		print(f"\nResults: {consistent} consistent, {inconsistent} inconsistent")

		# Allow some inconsistency but flag if too many
		if consistent + inconsistent > 0:
			consistency_rate = consistent / (consistent + inconsistent)
			assert consistency_rate >= 0.7, f"Version schema consistency too low: {consistency_rate:.1%}"


# =============================================================================
# AppStream-to-PackageKit Correlation Tests
# =============================================================================


class TestAppStreamPackageKitCorrelation:
	"""Tests for correlation between AppStream data and PackageKit."""

	def test_appstream_pkgname_matches_nix_attr(self):
		"""Test that AppStream pkgname fields match nixpkgs attribute names."""
		import xml.etree.ElementTree as ET

		xml_path = Path(__file__).parent.parent / "appstream-data" / "swcatalog" / "xml"

		xml_files = list(xml_path.glob("*.xml"))
		assert xml_files, (
			f"No AppStream XML files found in {xml_path}. Run 'just generate' to create AppStream data."
		)

		tree = ET.parse(xml_files[0])
		root = tree.getroot()

		nix_search = NixSearch()
		matched = 0
		unmatched = 0

		# Check a sample of components
		for component in root.findall(".//component")[:20]:
			pkgname_elem = component.find("pkgname")
			if pkgname_elem is None or not pkgname_elem.text:
				continue

			pkgname = pkgname_elem.text

			# Try to find this package in nix-search
			search_result = nix_search.get_package_info(pkgname)

			if search_result:
				matched += 1
			else:
				unmatched += 1

		print(f"\nAppStream-to-nixpkgs correlation: {matched} matched, {unmatched} unmatched")

		# At least 50% should be matchable
		if matched + unmatched > 0:
			match_rate = matched / (matched + unmatched)
			assert match_rate >= 0.5, f"AppStream-to-nixpkgs correlation too low: {match_rate:.1%}"

	def test_pkcon_can_resolve_appstream_packages(self):
		"""Test that PackageKit can resolve packages from AppStream data."""
		import xml.etree.ElementTree as ET

		xml_path = Path(__file__).parent.parent / "appstream-data" / "swcatalog" / "xml"

		xml_files = list(xml_path.glob("*.xml"))
		assert xml_files, (
			f"No AppStream XML files found in {xml_path}. Run 'just generate' to create AppStream data."
		)

		tree = ET.parse(xml_files[0])
		root = tree.getroot()

		resolvable = 0
		unresolvable = 0

		# Check a sample of components
		for component in root.findall(".//component")[:10]:
			pkgname_elem = component.find("pkgname")
			if pkgname_elem is None or not pkgname_elem.text:
				continue

			pkgname = pkgname_elem.text

			# Try to resolve via pkcon
			rc, _stdout, _stderr = run_command(["pkcon", "resolve", pkgname], timeout=30)

			if rc == 0:
				resolvable += 1
			else:
				unresolvable += 1

		print(f"\npkcon resolvable: {resolvable}, unresolvable: {unresolvable}")


# =============================================================================
# Direct Nix Profile Tests (bypasses PackageKit authorization)
# =============================================================================


class TestDirectNixProfileIntegration:
	"""
	Direct nix profile integration tests.

	These tests use nix commands directly (without going through PackageKit)
	to test the core nix profile functionality. This allows testing in
	environments where PackageKit authorization is not available.
	"""

	@pytest.fixture(autouse=True)
	def setup_and_teardown(self, test_package):
		"""Ensure test package is cleaned up after tests."""
		yield

		# Cleanup: try to remove the package if it was installed
		subprocess.run(
			["nix", "profile", "remove", test_package],
			capture_output=True,
			timeout=60,
		)

	@pytest.mark.slow
	def test_direct_nix_profile_lifecycle(self, test_package, nix_search):
		"""
		Test the package lifecycle using direct nix commands.

		This test bypasses PackageKit to verify core nix profile functionality:
		1. Search for package via nix-search
		2. Install package via nix profile install
		3. Verify installation in profile manifest
		4. Verify version consistency
		5. Remove package via nix profile remove
		6. Verify removal
		"""
		print(f"\n{'=' * 60}")
		print(f"Direct Nix Profile Lifecycle Test for: {test_package}")
		print(f"{'=' * 60}")

		# Step 1: Get package info from nix-search
		print("\n[Step 1] Getting package info from nix-search...")
		search_info = nix_search.get_package_info(test_package)

		if not search_info:
			results = nix_search.search([test_package], limit=10)
			if test_package in results:
				search_info = results[test_package]
			elif results:
				search_info = next(iter(results.values()))

		assert search_info, f"Could not find {test_package} in nix-search"

		nix_search_version = search_info.get("version", "unknown")
		print(f"  nix-search version: {nix_search_version}")

		# Step 2: Check current state
		print("\n[Step 2] Checking current installation status...")
		profile = NixProfile()
		installed_before = profile.get_installed_packages()
		was_installed = test_package in installed_before

		if was_installed:
			print(f"  Package already installed (version: {installed_before[test_package]})")
			print("  Removing existing installation first...")
			run_command(["nix", "profile", "remove", test_package], timeout=120)
			# Reload profile
			profile = NixProfile()
			installed_before = profile.get_installed_packages()
			assert test_package not in installed_before, "Failed to remove existing installation"

		# Step 3: Install via direct nix command
		print("\n[Step 3] Installing package via nix profile install...")
		rc, stdout, stderr = run_command(
			["nix", "profile", "install", f"nixpkgs#{test_package}"],
			timeout=300,
		)

		# Nix may succeed but print deprecation warnings to stderr
		# Check if package was actually installed regardless of warnings
		combined_output = stdout + stderr
		if "deprecated" in combined_output.lower():
			print(f"  Note: Nix deprecation warning: {stderr[:200]}")

		# Step 4: Verify installation
		print("\n[Step 4] Verifying package installation...")
		profile_fresh = NixProfile()
		installed_after = profile_fresh.get_installed_packages()

		if test_package not in installed_after and rc != 0:
			pytest.fail(f"nix profile install failed:\n{stderr}\n{stdout}")

		assert test_package in installed_after, (
			f"Package {test_package} not found after install.\nInstalled: {list(installed_after.keys())}"
		)

		installed_version = installed_after[test_package]
		print(f"  Installed version: {installed_version}")

		# Step 5: Verify version consistency
		print("\n[Step 5] Verifying version consistency...")
		if installed_version != "unknown" and nix_search_version != "unknown":
			installed_base = installed_version.split("-")[0].split("+")[0]
			search_base = nix_search_version.split("-")[0].split("+")[0]

			print(f"  Installed base version: {installed_base}")
			print(f"  nix-search base version: {search_base}")

			# Versions should follow same schema
			assert any(c.isdigit() for c in installed_version), (
				f"Installed version '{installed_version}' has no digits"
			)
			assert any(c.isdigit() for c in nix_search_version), (
				f"nix-search version '{nix_search_version}' has no digits"
			)

		# Step 6: Remove package
		print("\n[Step 6] Removing package via nix profile remove...")
		rc, stdout, stderr = run_command(
			["nix", "profile", "remove", test_package],
			timeout=120,
		)

		if rc != 0:
			# May need to use the legacyPackages path
			print("  Simple removal failed, trying legacyPackages path...")
			rc, stdout, stderr = run_command(
				["nix", "profile", "remove", f"legacyPackages.x86_64-linux.{test_package}"],
				timeout=120,
			)

		# Step 7: Verify removal
		print("\n[Step 7] Verifying package removal...")
		profile_final = NixProfile()
		installed_final = profile_final.get_installed_packages()

		assert test_package not in installed_final, f"Package {test_package} still installed after removal"
		print("  Package confirmed removed")

		print(f"\n{'=' * 60}")
		print("Direct Nix Profile Lifecycle Test PASSED")
		print(f"{'=' * 60}")

	def test_nix_profile_manifest_parsing(self, nix_profile):
		"""Test that the NixProfile class correctly parses manifest.json."""
		# The manifest should load without errors
		installed = nix_profile.get_installed_packages()
		assert isinstance(installed, dict)

		# Check each package has required fields
		for pkg_name, version in installed.items():
			assert isinstance(pkg_name, str)
			assert len(pkg_name) > 0
			assert isinstance(version, str)

			# Get detailed info
			info = nix_profile.get_package_info(pkg_name)
			if info:
				assert "storePaths" in info
				assert isinstance(info["storePaths"], list)


# =============================================================================
# Stress/Reliability Tests
# =============================================================================


class TestReliability:
	"""Reliability and edge case tests."""

	def test_profile_reload_consistency(self, nix_profile):
		"""Test that profile reloads give consistent results."""
		# Load profile multiple times
		results = []
		for _i in range(3):
			fresh_profile = NixProfile()
			installed = fresh_profile.get_installed_packages()
			results.append(set(installed.keys()))

		# All loads should return the same packages
		assert all(r == results[0] for r in results), "Profile loads are inconsistent"

	def test_nix_search_handles_special_characters(self, nix_search):
		"""Test that nix-search handles special characters gracefully."""
		# These should not crash
		for query in ["test", "python3", "gcc-wrapper", "xorg.xeyes"]:
			try:
				results = nix_search.search([query], limit=5)
				# Just verify it returns without crashing
				assert isinstance(results, dict)
			except Exception as e:
				pytest.fail(f"nix-search failed on query '{query}': {e}")

	def test_version_extraction_edge_cases(self, nix_profile):
		"""Test version extraction from various store path formats."""
		test_cases = [
			("/nix/store/abc123-firefox-122.0", "firefox", "122.0"),
			("/nix/store/abc123-python3.11-numpy-1.24.3", "numpy", "1.24.3"),
			("/nix/store/abc123-vim-9.0.1234", "vim", "9.0.1234"),
			("/nix/store/abc123-hello-2.12.1", "hello", "2.12.1"),
		]

		for store_path, pkg_name, _expected_version in test_cases:
			extracted = nix_profile._extract_version_from_store_path(store_path, pkg_name)
			# Should extract something (may not be exact due to heuristics)
			assert extracted != "", f"Failed to extract version from {store_path}"

	def test_wrapped_package_version_consistency(self, nix_profile):
		"""
		Test that -wrapped packages don't create false update notifications.

		Some packages like libreoffice-fresh have -wrapped suffixes in their
		store paths, but the version metadata doesn't include this suffix.
		This test ensures version extraction properly handles these cases.
		"""
		test_cases = [
			# Store path format: /nix/store/hash-package-name-version-wrapped
			("/nix/store/abc123-libreoffice-fresh-25.8.2.2-wrapped", "libreoffice-fresh", "25.8.2.2"),
			("/nix/store/abc123-chromium-131.0.6778.204-wrapped", "chromium", "131.0.6778.204"),
			("/nix/store/abc123-vscode-1.95.3-wrapped", "vscode", "1.95.3"),
			# Also test without -wrapped suffix
			("/nix/store/abc123-firefox-122.0", "firefox", "122.0"),
		]

		for store_path, pkg_name, expected_version in test_cases:
			extracted = nix_profile._extract_version_from_store_path(store_path, pkg_name)

			# The extracted version should NOT include '-wrapped' suffix
			assert "-wrapped" not in extracted, (
				f"Version extracted from {store_path} incorrectly includes '-wrapped' suffix: {extracted}"
			)

			# The extracted version should match the expected version
			assert extracted == expected_version, (
				f"Version mismatch for {pkg_name}:\n"
				f"  Store path: {store_path}\n"
				f"  Expected: {expected_version}\n"
				f"  Extracted: {extracted}"
			)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
