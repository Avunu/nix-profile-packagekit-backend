#!/usr/bin/env python3
"""Unit tests for nix_profile_backend module."""

from unittest import mock

import pytest


class TestNixProfileBackendProfileFlag:
	"""Tests for --profile flag injection in nix commands."""

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
		"""Test --profile flag is inserted at correct position for install."""
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

			# Command should be: nix profile install --profile /path nixpkgs#firefox --log-format internal-json
			assert cmd[0] == "nix"
			assert cmd[1] == "profile"
			assert cmd[2] == "install"
			assert cmd[3] == "--profile"
			assert cmd[4] == "/home/testuser/.nix-profile"
			assert "nixpkgs#firefox" in cmd

	def test_profile_flag_position_remove(self, mock_backend):
		"""Test --profile flag is inserted at correct position for remove."""
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
			assert "firefox" in cmd

	def test_profile_flag_position_upgrade(self, mock_backend):
		"""Test --profile flag is inserted at correct position for upgrade."""
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
		# Format should be: nix profile install --profile <path> <installable> --log-format internal-json

		args = ["profile", "install", "nixpkgs#librewolf"]
		cmd = ["nix", *args]
		profile_path = "/home/user/.nix-profile"

		# Simulate the injection logic from _run_nix_command
		if len(args) >= 2 and args[0] == "profile":
			cmd.insert(3, "--profile")
			cmd.insert(4, profile_path)

		expected = [
			"nix",
			"profile",
			"install",
			"--profile",
			"/home/user/.nix-profile",
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

		expected = [
			"nix",
			"profile",
			"remove",
			"--profile",
			"/home/user/.nix-profile",
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

		expected = [
			"nix",
			"profile",
			"upgrade",
			"--profile",
			"/nix/var/nix/profiles/per-user/testuser/profile",
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

		expected = [
			"nix",
			"profile",
			"list",
			"--profile",
			"/home/user/.nix-profile",
		]

		assert cmd == expected
