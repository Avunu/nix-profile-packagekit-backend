#!/usr/bin/env python3
"""Unit tests for nix_search module."""

from unittest import mock

import pytest

from nix_search import NixSearch


class TestNixSearch:
    """Tests for NixSearch class."""

    def test_init_default_channel(self):
        """Test default channel is unstable."""
        search = NixSearch()
        assert search.channel == "unstable"

    def test_init_custom_channel(self):
        """Test custom channel."""
        search = NixSearch(channel="24.05")
        assert search.channel == "24.05"

    def test_parse_package(self):
        """Test parsing nix-search-cli JSON output."""
        search = NixSearch()
        
        raw_pkg = {
            "package_attr_name": "firefox",
            "package_pname": "firefox",
            "package_pversion": "122.0",
            "package_description": "A web browser",
            "package_homepage": ["https://firefox.com"],
            "package_license": [{"fullName": "Mozilla Public License 2.0"}],
            "package_programs": ["firefox"],
            "package_outputs": ["out"],
        }
        
        parsed = search._parse_package(raw_pkg)
        
        assert parsed["pname"] == "firefox"
        assert parsed["version"] == "122.0"
        assert parsed["description"] == "A web browser"
        assert parsed["homepage"] == "https://firefox.com"
        assert parsed["license"] == "Mozilla Public License 2.0"
        assert parsed["programs"] == ["firefox"]

    def test_parse_package_missing_fields(self):
        """Test parsing with missing optional fields."""
        search = NixSearch()
        
        raw_pkg = {
            "package_attr_name": "somepackage",
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
            stdout='{"package_attr_name": "firefox", "package_pversion": "122.0"}\n',
            stderr=""
        )
        
        search = NixSearch()
        results = search.search(["firefox"])
        
        assert "firefox" in results
        assert results["firefox"]["version"] == "122.0"
        
        # Verify command
        call_args = mock_run.call_args[0][0]
        assert "nix-search" in call_args
        assert "--search" in call_args
        assert "firefox" in call_args

    @mock.patch("subprocess.run")
    def test_search_by_name(self, mock_run):
        """Test search_by_name method."""
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout='{"package_attr_name": "vim", "package_pversion": "9.0"}\n',
            stderr=""
        )
        
        search = NixSearch()
        results = search.search_by_name("vim")
        
        assert "vim" in results
        
        call_args = mock_run.call_args[0][0]
        assert "--name" in call_args
        assert "vim" in call_args

    @mock.patch("subprocess.run")
    def test_search_timeout(self, mock_run):
        """Test search handles timeout gracefully."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("nix-search", 30)
        
        search = NixSearch()
        results = search.search(["firefox"])
        
        assert results == {}

    @mock.patch("subprocess.run")
    def test_get_package_info_caching(self, mock_run):
        """Test that get_package_info caches results."""
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout='{"package_attr_name": "git", "package_pversion": "2.43"}\n',
            stderr=""
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
