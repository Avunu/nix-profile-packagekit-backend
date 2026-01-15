#!/usr/bin/env python3
"""Unit tests for nix_profile module."""

import json
import tempfile
from pathlib import Path
from unittest import mock

from nix_profile import NixProfile


class TestNixProfileUserResolution:
	"""Tests for user profile resolution (PackageKit UID handling)."""

	def test_resolve_profile_from_packagekit_uid(self):
		"""Test that UID env var from PackageKit resolves to correct user profile."""
		# Get current user info to use in test
		current_uid = 1000  # typical user UID
		mock_pw = mock.MagicMock()
		mock_pw.pw_name = "testuser"
		mock_pw.pw_dir = "/home/testuser"

		with mock.patch.dict("os.environ", {"UID": str(current_uid)}, clear=True):
			with mock.patch("pwd.getpwuid", return_value=mock_pw) as mock_getpwuid:
				with mock.patch("os.path.exists", return_value=True):
					profile = NixProfile()

					# Should have called getpwuid with the UID from env
					mock_getpwuid.assert_called_once_with(current_uid)
					# Should use the user's home profile
					assert profile.profile_path == Path("/home/testuser/.nix-profile")

	def test_resolve_profile_uid_fallback_to_per_user(self):
		"""Test fallback to per-user profile when home profile doesn't exist."""
		mock_pw = mock.MagicMock()
		mock_pw.pw_name = "testuser"
		mock_pw.pw_dir = "/home/testuser"

		with mock.patch.dict("os.environ", {"UID": "1000"}, clear=True):
			with mock.patch("pwd.getpwuid", return_value=mock_pw):
				with mock.patch("os.path.exists", return_value=False):
					profile = NixProfile()
					assert profile.profile_path == Path("/nix/var/nix/profiles/per-user/testuser/profile")

	def test_resolve_profile_no_uid_uses_home(self):
		"""Test that without UID, HOME env var is used."""
		with mock.patch.dict("os.environ", {"HOME": "/home/anotheruser"}, clear=True):
			profile = NixProfile()
			assert profile.profile_path == Path("/home/anotheruser/.nix-profile")

	def test_resolve_profile_ignores_root_home(self):
		"""Test that HOME=/root is ignored (indicates daemon context)."""
		with mock.patch.dict("os.environ", {"HOME": "/root", "USER": "testuser"}, clear=True):
			profile = NixProfile()
			# Should fall back to per-user profile, not /root/.nix-profile
			assert profile.profile_path == Path("/nix/var/nix/profiles/per-user/testuser/profile")

	def test_resolve_profile_sudo_user_fallback(self):
		"""Test SUDO_USER fallback when no UID or HOME."""
		with mock.patch.dict("os.environ", {"SUDO_USER": "sudouser"}, clear=True):
			profile = NixProfile()
			assert profile.profile_path == Path("/nix/var/nix/profiles/per-user/sudouser/profile")

	def test_resolve_profile_invalid_uid(self):
		"""Test graceful handling of invalid UID."""
		with mock.patch.dict("os.environ", {"UID": "invalid", "HOME": "/home/fallback"}, clear=True):
			profile = NixProfile()
			# Should fall back to HOME
			assert profile.profile_path == Path("/home/fallback/.nix-profile")

	def test_resolve_profile_uid_user_not_found(self):
		"""Test graceful handling when UID doesn't map to a user."""
		with mock.patch.dict("os.environ", {"UID": "99999", "HOME": "/home/fallback"}, clear=True):
			with mock.patch("pwd.getpwuid", side_effect=KeyError("user not found")):
				profile = NixProfile()
				# Should fall back to HOME
				assert profile.profile_path == Path("/home/fallback/.nix-profile")


class TestNixProfile:
	"""Tests for NixProfile class."""

	def test_init_custom_path(self):
		"""Test custom profile path."""
		profile = NixProfile("/custom/path")
		assert profile.profile_path == Path("/custom/path")

	def test_get_installed_packages_no_manifest(self):
		"""Test empty result when manifest doesn't exist."""
		with tempfile.TemporaryDirectory() as tmpdir:
			profile = NixProfile(tmpdir)
			assert profile.get_installed_packages() == {}

	def test_get_installed_packages_empty_manifest(self):
		"""Test empty manifest returns empty dict."""
		with tempfile.TemporaryDirectory() as tmpdir:
			manifest = Path(tmpdir) / "manifest.json"
			manifest.write_text(json.dumps({"version": 2, "elements": []}))

			profile = NixProfile(tmpdir)
			assert profile.get_installed_packages() == {}

	def test_get_installed_packages_v2_format(self):
		"""Test parsing v2 manifest (list-based elements)."""
		manifest_data = {
			"version": 2,
			"elements": [
				{
					"attrPath": "firefox",
					"storePaths": ["/nix/store/abc123-firefox-122.0"],
					"originalUrl": "nixpkgs#firefox",
				},
				{
					"attrPath": "vim",
					"storePaths": ["/nix/store/def456-vim-9.0.1"],
					"originalUrl": "nixpkgs#vim",
				},
			],
		}

		with tempfile.TemporaryDirectory() as tmpdir:
			manifest = Path(tmpdir) / "manifest.json"
			manifest.write_text(json.dumps(manifest_data))

			profile = NixProfile(tmpdir)
			packages = profile.get_installed_packages()

			assert "firefox" in packages
			assert "vim" in packages
			assert packages["firefox"] == "122.0"
			assert packages["vim"] == "9.0.1"

	def test_get_installed_packages_v3_format(self):
		"""Test parsing v3 manifest (dict-based elements)."""
		manifest_data = {
			"version": 3,
			"elements": {
				"firefox": {
					"active": True,
					"attrPath": "legacyPackages.x86_64-linux.firefox",
					"storePaths": ["/nix/store/abc123-firefox-122.0"],
					"originalUrl": "flake:nixpkgs",
					"priority": 5,
				},
				"vim": {
					"active": True,
					"attrPath": "legacyPackages.x86_64-linux.vim",
					"storePaths": ["/nix/store/def456-vim-9.0.1"],
					"originalUrl": "flake:nixpkgs",
					"priority": 5,
				},
				"disabled-pkg": {
					"active": False,
					"attrPath": "legacyPackages.x86_64-linux.disabled",
					"storePaths": ["/nix/store/xyz-disabled-1.0"],
					"originalUrl": "flake:nixpkgs",
					"priority": 5,
				},
			},
		}

		with tempfile.TemporaryDirectory() as tmpdir:
			manifest = Path(tmpdir) / "manifest.json"
			manifest.write_text(json.dumps(manifest_data))

			profile = NixProfile(tmpdir)
			packages = profile.get_installed_packages()

			assert "firefox" in packages
			assert "vim" in packages
			assert packages["firefox"] == "122.0"
			assert packages["vim"] == "9.0.1"
			# Inactive packages should be excluded
			assert "disabled" not in packages
			assert "disabled-pkg" not in packages

	def test_find_package_index_v2(self):
		"""Test finding package index in v2 manifest."""
		manifest_data = {
			"version": 2,
			"elements": [
				{"attrPath": "firefox", "storePaths": []},
				{"attrPath": "vim", "storePaths": []},
				{"attrPath": "git", "storePaths": []},
			],
		}

		with tempfile.TemporaryDirectory() as tmpdir:
			manifest = Path(tmpdir) / "manifest.json"
			manifest.write_text(json.dumps(manifest_data))

			profile = NixProfile(tmpdir)

			# v2 normalized to v3 returns keys, not indices
			assert profile.find_package_index("firefox") == "firefox"
			assert profile.find_package_index("vim") == "vim"
			assert profile.find_package_index("git") == "git"
			assert profile.find_package_index("nonexistent") is None

	def test_find_package_index_v3(self):
		"""Test finding package key in v3 manifest."""
		manifest_data = {
			"version": 3,
			"elements": {
				"firefox": {
					"active": True,
					"attrPath": "legacyPackages.x86_64-linux.firefox",
					"storePaths": [],
				},
				"my-vim": {
					"active": True,
					"attrPath": "legacyPackages.x86_64-linux.vim",
					"storePaths": [],
				},
			},
		}

		with tempfile.TemporaryDirectory() as tmpdir:
			manifest = Path(tmpdir) / "manifest.json"
			manifest.write_text(json.dumps(manifest_data))

			profile = NixProfile(tmpdir)

			# Can find by simple name (from attrPath)
			assert profile.find_package_index("firefox") == "firefox"
			assert profile.find_package_index("vim") == "my-vim"  # Found by attrPath suffix
			# Can also find by key name
			assert profile.find_package_index("my-vim") == "my-vim"
			assert profile.find_package_index("nonexistent") is None

	def test_extract_version_from_store_path(self):
		"""Test version extraction from store paths."""
		profile = NixProfile.__new__(NixProfile)

		# Standard format
		assert (
			profile._extract_version_from_store_path("/nix/store/abc123-firefox-122.0", "firefox") == "122.0"
		)

		# With patch version
		assert profile._extract_version_from_store_path("/nix/store/abc123-vim-9.0.1234", "vim") == "9.0.1234"

	def test_is_empty(self):
		"""Test is_empty check."""
		with tempfile.TemporaryDirectory() as tmpdir:
			profile = NixProfile(tmpdir)

			# No manifest = empty
			assert profile.is_empty() is True

			# Empty elements = empty
			manifest = Path(tmpdir) / "manifest.json"
			manifest.write_text(json.dumps({"elements": []}))
			assert profile.is_empty() is True

			# Has elements = not empty
			manifest.write_text(json.dumps({"elements": [{"attrPath": "foo"}]}))
			assert profile.is_empty() is False
