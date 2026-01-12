#!/usr/bin/env python3
"""Unit tests for nix_profile module."""

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from nix_profile import NixProfile


class TestNixProfile:
    """Tests for NixProfile class."""

    def test_init_default_path(self):
        """Test default profile path uses HOME."""
        with mock.patch.dict("os.environ", {"HOME": "/home/testuser"}):
            profile = NixProfile()
            assert profile.profile_path == Path("/home/testuser/.nix-profile")

    def test_init_custom_path(self):
        """Test custom profile path."""
        profile = NixProfile("/custom/path")
        assert profile.profile_path == Path("/custom/path")

    def test_init_no_home_raises(self):
        """Test that missing HOME raises ValueError."""
        with mock.patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="HOME"):
                NixProfile()

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

    def test_get_installed_packages_with_packages(self):
        """Test parsing manifest with packages."""
        manifest_data = {
            "version": 2,
            "elements": [
                {
                    "attrPath": "firefox",
                    "storePaths": ["/nix/store/abc123-firefox-122.0"],
                    "originalUrl": "nixpkgs#firefox"
                },
                {
                    "attrPath": "vim",
                    "storePaths": ["/nix/store/def456-vim-9.0.1"],
                    "originalUrl": "nixpkgs#vim"
                }
            ]
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

    def test_find_package_index(self):
        """Test finding package index in manifest."""
        manifest_data = {
            "version": 2,
            "elements": [
                {"attrPath": "firefox", "storePaths": []},
                {"attrPath": "vim", "storePaths": []},
                {"attrPath": "git", "storePaths": []},
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "manifest.json"
            manifest.write_text(json.dumps(manifest_data))
            
            profile = NixProfile(tmpdir)
            
            assert profile.find_package_index("firefox") == 0
            assert profile.find_package_index("vim") == 1
            assert profile.find_package_index("git") == 2
            assert profile.find_package_index("nonexistent") is None

    def test_extract_version_from_store_path(self):
        """Test version extraction from store paths."""
        profile = NixProfile.__new__(NixProfile)
        
        # Standard format
        assert profile._extract_version_from_store_path(
            "/nix/store/abc123-firefox-122.0", "firefox"
        ) == "122.0"
        
        # With patch version
        assert profile._extract_version_from_store_path(
            "/nix/store/abc123-vim-9.0.1234", "vim"
        ) == "9.0.1234"

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
