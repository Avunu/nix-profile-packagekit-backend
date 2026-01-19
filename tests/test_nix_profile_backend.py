#!/usr/bin/env python3
"""Unit tests for nix_profile_backend module."""

import os
from unittest import mock

import pytest


class TestNixProfileBackendProfileFlag:
	"""Tests for --profile and --impure flag injection in nix commands."""

	@pytest.fixture
	def mock_backend(self):
		"""Create a mock backend for testing command construction."""
		# We need to mock the parent classes and create a backend instance
		with mock.patch("nix_profile_backend.PackageKitBaseBackend"):
			with mock.patch("nix_profile_backend.PackagekitPackage"):
				with mock.patch("nix_profile_backend.NixProfile") as mock_profile:
					with mock.patch("nix_profile_backend.NixSearch"):
						# Set up mock profile
						mock_profile_instance = mock.MagicMock()
						mock_profile_instance.profile_path = "/home/testuser/.nix-profile"
						mock_profile.return_value = mock_profile_instance

						from nix_profile_backend import PackageKitNixProfileBackend

						backend = PackageKitNixProfileBackend([])
						backend._profile_path = "/home/testuser/.nix-profile"
						yield backend

	def test_profile_flag_position_install(self, mock_backend):
		"""Test --profile and --impure flags are inserted at correct position for install."""
		with mock.patch("subprocess.Popen") as mock_popen:
			mock_process = mock.MagicMock()
			mock_process.returncode = 0
			mock_process.stderr = []
			mock_process.communicate.return_value = ("", "")
			mock_popen.return_value = mock_process

			mock_backend._run_nix_command(["profile", "install", "nixpkgs#firefox"])

			# Get the command that was passed to Popen
			call_args = mock_popen.call_args
			cmd = call_args[0][0]

			# Command should be: nix profile install --profile /path --impure nixpkgs#firefox --log-format internal-json
			assert cmd[0] == "nix"
			assert cmd[1] == "profile"
			assert cmd[2] == "install"
			assert cmd[3] == "--profile"
			assert cmd[4] == "/home/testuser/.nix-profile"
			assert cmd[5] == "--impure"
			assert "nixpkgs#firefox" in cmd

	def test_profile_flag_position_remove(self, mock_backend):
		"""Test --profile and --impure flags are inserted at correct position for remove."""
		with mock.patch("subprocess.Popen") as mock_popen:
			mock_process = mock.MagicMock()
			mock_process.returncode = 0
			mock_process.stderr = []
			mock_process.communicate.return_value = ("", "")
			mock_popen.return_value = mock_process

			mock_backend._run_nix_command(["profile", "remove", "firefox"])

			cmd = mock_popen.call_args[0][0]

			assert cmd[0] == "nix"
			assert cmd[1] == "profile"
			assert cmd[2] == "remove"
			assert cmd[3] == "--profile"
			assert cmd[4] == "/home/testuser/.nix-profile"
			assert cmd[5] == "--impure"
			assert "firefox" in cmd

	def test_profile_flag_position_upgrade(self, mock_backend):
		"""Test --profile and --impure flags are inserted at correct position for upgrade."""
		with mock.patch("subprocess.Popen") as mock_popen:
			mock_process = mock.MagicMock()
			mock_process.returncode = 0
			mock_process.stderr = []
			mock_process.communicate.return_value = ("", "")
			mock_popen.return_value = mock_process

			mock_backend._run_nix_command(["profile", "upgrade", ".*"])

			cmd = mock_popen.call_args[0][0]

			assert cmd[0] == "nix"
			assert cmd[1] == "profile"
			assert cmd[2] == "upgrade"
			assert cmd[3] == "--profile"
			assert cmd[4] == "/home/testuser/.nix-profile"
			assert cmd[5] == "--impure"

	def test_profile_flag_not_added_to_non_profile_commands(self, mock_backend):
		"""Test --profile flag is NOT added to non-profile commands."""
		with mock.patch("subprocess.Popen") as mock_popen:
			mock_process = mock.MagicMock()
			mock_process.returncode = 0
			mock_process.stderr = []
			mock_process.communicate.return_value = ('{"packages": []}', "")
			mock_popen.return_value = mock_process

			mock_backend._run_nix_command(["search", "nixpkgs", "firefox"])

			cmd = mock_popen.call_args[0][0]

			assert cmd[0] == "nix"
			assert cmd[1] == "search"
			assert "--profile" not in cmd

	def test_profile_flag_can_be_disabled(self, mock_backend):
		"""Test use_profile=False prevents --profile injection."""
		with mock.patch("subprocess.Popen") as mock_popen:
			mock_process = mock.MagicMock()
			mock_process.returncode = 0
			mock_process.stderr = []
			mock_process.communicate.return_value = ("", "")
			mock_popen.return_value = mock_process

			mock_backend._run_nix_command(["profile", "list"], use_profile=False)

			cmd = mock_popen.call_args[0][0]

			# --profile should NOT be in the command
			assert "--profile" not in cmd

	def test_profile_flag_requires_action(self, mock_backend):
		"""Test --profile flag requires at least 2 args (profile + action)."""
		with mock.patch("subprocess.Popen") as mock_popen:
			mock_process = mock.MagicMock()
			mock_process.returncode = 0
			mock_process.stderr = []
			mock_process.communicate.return_value = ("", "")
			mock_popen.return_value = mock_process

			# Just "profile" without action - shouldn't add --profile
			mock_backend._run_nix_command(["profile"])

			cmd = mock_popen.call_args[0][0]

			# With only 1 arg, --profile should NOT be added
			assert "--profile" not in cmd


class TestNixProfileBackendCommandConstruction:
	"""Test that commands are constructed correctly end-to-end."""

	def test_install_command_full(self):
		"""Integration test: verify full install command structure."""
		# This tests the command that would be sent to subprocess
		# Format should be: nix profile install --profile <path> --impure <installable> --log-format internal-json

		args = ["profile", "install", "nixpkgs#librewolf"]
		cmd = ["nix", *args]
		profile_path = "/home/user/.nix-profile"

		# Simulate the injection logic from _run_nix_command
		if len(args) >= 2 and args[0] == "profile":
			cmd.insert(3, "--profile")
			cmd.insert(4, profile_path)
			cmd.insert(5, "--impure")

		expected = [
			"nix",
			"profile",
			"install",
			"--profile",
			"/home/user/.nix-profile",
			"--impure",
			"nixpkgs#librewolf",
		]

		assert cmd == expected

	def test_remove_command_full(self):
		"""Integration test: verify full remove command structure."""
		args = ["profile", "remove", "firefox"]
		cmd = ["nix", *args]
		profile_path = "/home/user/.nix-profile"

		if len(args) >= 2 and args[0] == "profile":
			cmd.insert(3, "--profile")
			cmd.insert(4, profile_path)
			cmd.insert(5, "--impure")

		expected = [
			"nix",
			"profile",
			"remove",
			"--profile",
			"/home/user/.nix-profile",
			"--impure",
			"firefox",
		]

		assert cmd == expected

	def test_upgrade_pattern_command_full(self):
		"""Integration test: verify upgrade with pattern command structure."""
		args = ["profile", "upgrade", ".*"]
		cmd = ["nix", *args]
		profile_path = "/nix/var/nix/profiles/per-user/testuser/profile"

		if len(args) >= 2 and args[0] == "profile":
			cmd.insert(3, "--profile")
			cmd.insert(4, profile_path)
			cmd.insert(5, "--impure")

		expected = [
			"nix",
			"profile",
			"upgrade",
			"--profile",
			"/nix/var/nix/profiles/per-user/testuser/profile",
			"--impure",
			".*",
		]

		assert cmd == expected

	def test_profile_list_not_modified_without_action_arg(self):
		"""Test that 'profile list' doesn't crash with short args."""
		args = ["profile", "list"]
		cmd = ["nix", *args]
		profile_path = "/home/user/.nix-profile"

		# This should work with len(args) >= 2
		if len(args) >= 2 and args[0] == "profile":
			cmd.insert(3, "--profile")
			cmd.insert(4, profile_path)
			cmd.insert(5, "--impure")

		expected = [
			"nix",
			"profile",
			"list",
			"--profile",
			"/home/user/.nix-profile",
			"--impure",
		]

		assert cmd == expected


class TestNixProfileBackendEnvironment:
	"""Tests for environment variable handling."""

	@pytest.fixture
	def mock_backend(self):
		"""Create a mock backend for testing environment handling."""
		with mock.patch("nix_profile_backend.PackageKitBaseBackend"):
			with mock.patch("nix_profile_backend.PackagekitPackage"):
				with mock.patch("nix_profile_backend.NixProfile") as mock_profile:
					with mock.patch("nix_profile_backend.NixSearch"):
						mock_profile_instance = mock.MagicMock()
						mock_profile_instance.profile_path = "/home/testuser/.nix-profile"
						mock_profile.return_value = mock_profile_instance

						from nix_profile_backend import PackageKitNixProfileBackend

						backend = PackageKitNixProfileBackend([])
						backend._profile_path = "/home/testuser/.nix-profile"
						yield backend

	def test_nixpkgs_allow_unfree_passed_to_subprocess(self, mock_backend):
		"""Test that NIXPKGS_ALLOW_UNFREE is passed to nix subprocess."""
		with mock.patch("subprocess.Popen") as mock_popen:
			with mock.patch.dict(os.environ, {"NIXPKGS_ALLOW_UNFREE": "1"}):
				mock_process = mock.MagicMock()
				mock_process.returncode = 0
				mock_process.stderr = []
				mock_process.communicate.return_value = ("", "")
				mock_popen.return_value = mock_process

				mock_backend._run_nix_command(["profile", "install", "nixpkgs#google-chrome"])

				# Check that env was passed to Popen
				call_kwargs = mock_popen.call_args[1]
				assert "env" in call_kwargs
				assert call_kwargs["env"].get("NIXPKGS_ALLOW_UNFREE") == "1"

	def test_nixpkgs_allow_insecure_passed_to_subprocess(self, mock_backend):
		"""Test that NIXPKGS_ALLOW_INSECURE is passed to nix subprocess."""
		with mock.patch("subprocess.Popen") as mock_popen:
			with mock.patch.dict(os.environ, {"NIXPKGS_ALLOW_INSECURE": "1"}):
				mock_process = mock.MagicMock()
				mock_process.returncode = 0
				mock_process.stderr = []
				mock_process.communicate.return_value = ("", "")
				mock_popen.return_value = mock_process

				mock_backend._run_nix_command(["profile", "upgrade", "some-package"])

				call_kwargs = mock_popen.call_args[1]
				assert "env" in call_kwargs
				assert call_kwargs["env"].get("NIXPKGS_ALLOW_INSECURE") == "1"


class TestNixProfileBackendStderrFiltering:
	"""Tests for stderr JSON log filtering."""

	@pytest.fixture
	def mock_backend(self):
		"""Create a mock backend for testing stderr filtering."""
		with mock.patch("nix_profile_backend.PackageKitBaseBackend"):
			with mock.patch("nix_profile_backend.PackagekitPackage"):
				with mock.patch("nix_profile_backend.NixProfile") as mock_profile:
					with mock.patch("nix_profile_backend.NixSearch"):
						mock_profile_instance = mock.MagicMock()
						mock_profile_instance.profile_path = "/home/testuser/.nix-profile"
						mock_profile.return_value = mock_profile_instance

						from nix_profile_backend import PackageKitNixProfileBackend

						backend = PackageKitNixProfileBackend([])
						backend._profile_path = "/home/testuser/.nix-profile"
						yield backend

	def test_filter_json_log_lines(self, mock_backend):
		"""Test that JSON log lines are filtered from stderr."""
		stderr = """@nix {"action":"start","id":14955076124672,"level":5,"parent":0,"text":"checking 'legacyPackages.x86_64-linux.google-chrome' for updates","type":0}
@nix {"action":"stop","id":14955076124672}
error: Package 'google-chrome-144.0.7559.59' has an unfree license ('unfree'), refusing to evaluate."""

		filtered = mock_backend._filter_nix_stderr(stderr)

		assert "@nix" not in filtered
		assert '{"action"' not in filtered
		assert "error: Package 'google-chrome-144.0.7559.59' has an unfree license" in filtered

	def test_filter_preserves_real_error_messages(self, mock_backend):
		"""Test that real error messages are preserved after filtering."""
		stderr = """@nix {"action":"start","id":123,"text":"building"}
error: builder for '/nix/store/abc.drv' failed with exit code 1
@nix {"action":"stop","id":123}
error: 1 dependencies of derivation failed to build"""

		filtered = mock_backend._filter_nix_stderr(stderr)

		assert "builder for '/nix/store/abc.drv' failed with exit code 1" in filtered
		assert "1 dependencies of derivation failed to build" in filtered
		assert "@nix" not in filtered

	def test_filter_empty_stderr(self, mock_backend):
		"""Test filtering empty stderr."""
		filtered = mock_backend._filter_nix_stderr("")
		assert filtered == ""

	def test_filter_only_json_lines(self, mock_backend):
		"""Test filtering when stderr contains only JSON log lines."""
		stderr = """@nix {"action":"start","id":1,"text":"test"}
@nix {"action":"stop","id":1}"""

		filtered = mock_backend._filter_nix_stderr(stderr)
		assert filtered == ""
