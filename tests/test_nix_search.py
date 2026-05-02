#!/usr/bin/env python3
"""Unit tests for nix_search module (diamondburned/nix-search with local index)."""

from unittest import mock

from nix_search import NixSearch


class TestNixSearch:
	"""Tests for NixSearch class."""

	def test_init_default_index_path(self):
		"""Test default index path."""
		search = NixSearch()
		assert search.index_path == "/var/cache/nix-search"

	def test_init_custom_index_path(self):
		"""Test custom index path."""
		search = NixSearch(index_path="/tmp/test-idx")
		assert search.index_path == "/tmp/test-idx"

	def test_extract_attr_with_hash(self):
		"""Test extracting attr name from path field."""
		search = NixSearch()
		assert search._extract_attr({"path": "nixpkgs#firefox"}) == "firefox"
		assert (
			search._extract_attr({"path": "nixpkgs#python3Packages.requests"}) == "python3Packages.requests"
		)

	def test_extract_attr_fallback(self):
		"""Test attr extraction fallback to name field."""
		search = NixSearch()
		assert search._extract_attr({"name": "firefox"}) == "firefox"
		assert search._extract_attr({}) == ""

	def test_parse_package(self):
		"""Test parsing diamondburned/nix-search JSON output."""
		search = NixSearch()

		raw_pkg = {
			"path": "nixpkgs#firefox",
			"name": "firefox",
			"version": "135.0.1",
			"description": "A web browser built from Firefox source tree",
			"license": ["MPL-2.0"],
			"mainProgram": "firefox",
		}

		parsed = search._parse_package(raw_pkg)

		assert parsed["pname"] == "firefox"
		assert parsed["version"] == "135.0.1"
		assert parsed["description"] == "A web browser built from Firefox source tree"
		assert parsed["license"] == "MPL-2.0"
		assert parsed["mainProgram"] == "firefox"

	def test_parse_package_missing_fields(self):
		"""Test parsing with missing optional fields."""
		search = NixSearch()

		raw_pkg = {
			"path": "nixpkgs#somepackage",
			"name": "somepackage",
		}

		parsed = search._parse_package(raw_pkg)

		assert parsed["pname"] == "somepackage"
		assert parsed["version"] == "unknown"
		assert parsed["license"] == "unknown"

	@mock.patch("subprocess.run")
	def test_search(self, mock_run):
		"""Test search method."""
		mock_run.return_value = mock.Mock(
			returncode=0,
			stdout='[{"path": "nixpkgs#firefox", "name": "firefox", "version": "135.0.1", "description": "Web browser"}]',
			stderr="",
		)

		search = NixSearch()
		results = search.search(["firefox"])

		assert "firefox" in results
		assert results["firefox"]["version"] == "135.0.1"

		# Verify command
		call_args = mock_run.call_args[0][0]
		assert "nix-search" in call_args
		assert "--json" in call_args
		assert "--index-path" in call_args
		assert "firefox" in call_args

	@mock.patch("subprocess.run")
	def test_search_by_name(self, mock_run):
		"""Test search_by_name method with exact flag."""
		mock_run.return_value = mock.Mock(
			returncode=0,
			stdout='[{"path": "nixpkgs#vim", "name": "vim", "version": "9.1"}]',
			stderr="",
		)

		search = NixSearch()
		results = search.search_by_name("vim")

		assert "vim" in results

		call_args = mock_run.call_args[0][0]
		assert "--exact" in call_args
		assert "vim" in call_args

	@mock.patch("subprocess.run")
	def test_search_timeout(self, mock_run):
		"""Test search handles timeout gracefully."""
		import subprocess

		mock_run.side_effect = subprocess.TimeoutExpired("nix-search", 10)

		search = NixSearch()
		results = search.search(["firefox"])

		assert results == {}

	@mock.patch("subprocess.run")
	def test_search_empty_query(self, mock_run):
		"""Test search with empty terms returns empty."""
		search = NixSearch()
		results = search.search([])

		assert results == {}
		mock_run.assert_not_called()

	@mock.patch("subprocess.run")
	def test_search_nonzero_exit(self, mock_run):
		"""Test search handles non-zero exit code."""
		mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="error")

		search = NixSearch()
		results = search.search(["nonexistent"])

		assert results == {}

	@mock.patch("subprocess.run")
	def test_get_package_info_caching(self, mock_run):
		"""Test that get_package_info caches results."""
		mock_run.return_value = mock.Mock(
			returncode=0,
			stdout='[{"path": "nixpkgs#git", "name": "git", "version": "2.43"}]',
			stderr="",
		)

		search = NixSearch()

		# First call
		info1 = search.get_package_info("git")
		assert info1 is not None
		assert mock_run.call_count == 1

		# Second call should use cache
		info2 = search.get_package_info("git")
		assert info2 == info1
		assert mock_run.call_count == 1  # No additional call

	@mock.patch("subprocess.run")
	def test_resolve_package(self, mock_run):
		"""Test resolve_package returns tuple of (attr, version)."""
		mock_run.return_value = mock.Mock(
			returncode=0,
			stdout='[{"path": "nixpkgs#htop", "name": "htop", "version": "3.3.0"}]',
			stderr="",
		)

		search = NixSearch()
		result = search.resolve_package("htop")

		assert result == ("htop", "3.3.0")

	@mock.patch("subprocess.run")
	def test_resolve_package_not_found(self, mock_run):
		"""Test resolve_package returns None when not found."""
		mock_run.return_value = mock.Mock(returncode=0, stdout="[]", stderr="")

		search = NixSearch()
		result = search.resolve_package("nonexistent-pkg-xyz")

		assert result is None


class TestVersionNormalization:
	"""Tests for version normalization in NixSearch."""

	def test_normalize_wrapped_suffix(self):
		"""Test that -wrapped suffix is stripped from versions."""
		search = NixSearch()
		assert search._normalize_version("25.8.2.2-wrapped") == "25.8.2.2"
		assert search._normalize_version("1.0.0-wrapped") == "1.0.0"
		assert search._normalize_version("131.0.6778.204-wrapped") == "131.0.6778.204"

	def test_normalize_unwrapped_suffix(self):
		"""Test that -unwrapped suffix is stripped from versions."""
		search = NixSearch()
		assert search._normalize_version("1.2.3-unwrapped") == "1.2.3"

	def test_normalize_regular_version(self):
		"""Test that versions without wrapper suffixes are unchanged."""
		search = NixSearch()
		assert search._normalize_version("1.2.3") == "1.2.3"
		assert search._normalize_version("122.0") == "122.0"
		assert search._normalize_version("2025.01.22") == "2025.01.22"

	def test_normalize_empty_version(self):
		"""Test that empty version strings are handled."""
		search = NixSearch()
		assert search._normalize_version("") == ""
		assert search._normalize_version(None) is None

	def test_normalize_version_with_other_suffixes(self):
		"""Test that other suffixes are NOT stripped (only wrapper suffixes)."""
		search = NixSearch()
		assert search._normalize_version("1.2.3-beta") == "1.2.3-beta"
		assert search._normalize_version("1.2.3-rc1") == "1.2.3-rc1"
		assert search._normalize_version("1.2.3-pre") == "1.2.3-pre"

	def test_parse_package_normalizes_version(self):
		"""Test that _parse_package normalizes versions with wrapper suffixes."""
		search = NixSearch()

		raw_pkg = {
			"path": "nixpkgs#libreoffice-fresh",
			"name": "libreoffice",
			"version": "25.8.2.2-wrapped",
			"description": "Office suite",
			"license": ["MPL-2.0"],
		}

		parsed = search._parse_package(raw_pkg)

		# Version should be normalized (without -wrapped)
		assert parsed["version"] == "25.8.2.2"
		assert "-wrapped" not in parsed["version"]
