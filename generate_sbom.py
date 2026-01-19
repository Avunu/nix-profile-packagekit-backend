#!/usr/bin/env python3
"""
Generate CycloneDX SBOM (Software Bill of Materials) for the project.

This script creates a CycloneDX 1.5 compliant SBOM in JSON format,
documenting all project components, dependencies, and metadata.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_git_commit() -> str:
	"""Get current git commit hash."""
	try:
		result = subprocess.run(
			["git", "rev-parse", "HEAD"],
			capture_output=True,
			text=True,
			check=True,
		)
		return result.stdout.strip()
	except (subprocess.CalledProcessError, FileNotFoundError):
		return "unknown"


def get_git_url() -> str:
	"""Get git repository URL."""
	try:
		result = subprocess.run(
			["git", "config", "--get", "remote.origin.url"],
			capture_output=True,
			text=True,
			check=True,
		)
		url = result.stdout.strip()
		# Convert SSH to HTTPS if needed
		if url.startswith("git@github.com:"):
			url = url.replace("git@github.com:", "https://github.com/")
		if url.endswith(".git"):
			url = url[:-4]
		return url
	except (subprocess.CalledProcessError, FileNotFoundError):
		return "https://github.com/Avunu/nix-profile-packagekit-backend"


def create_sbom() -> dict[str, Any]:
	"""Create CycloneDX SBOM structure."""
	timestamp = datetime.now(timezone.utc).isoformat()
	commit_hash = get_git_commit()
	repo_url = get_git_url()

	sbom = {
		"bomFormat": "CycloneDX",
		"specVersion": "1.5",
		"serialNumber": f"urn:uuid:packagekit-backend-nix-profile-{commit_hash[:8]}",
		"version": 1,
		"metadata": {
			"timestamp": timestamp,
			"tools": {
				"components": [
					{
						"type": "application",
						"author": "PackageKit Nix Backend Contributors",
						"name": "generate-sbom",
						"version": "1.0.0",
					}
				]
			},
			"component": {
				"type": "application",
				"bom-ref": "pkg:github/Avunu/nix-profile-packagekit-backend@1.0.0",
				"name": "packagekit-backend-nix-profile",
				"version": "1.0.0",
				"description": "PackageKit backend for Nix profile management",
				"licenses": [{"license": {"id": "GPL-2.0-or-later"}}],
				"externalReferences": [
					{
						"type": "vcs",
						"url": repo_url,
					},
					{
						"type": "website",
						"url": repo_url,
					},
					{
						"type": "issue-tracker",
						"url": f"{repo_url}/issues",
					},
				],
				"properties": [
					{"name": "cdx:nix:commit", "value": commit_hash},
				],
			},
		},
		"components": [
			{
				"type": "library",
				"bom-ref": "pkg:pypi/packagekit",
				"name": "packagekit",
				"description": "PackageKit Python bindings",
				"licenses": [{"license": {"id": "GPL-2.0-or-later"}}],
				"externalReferences": [
					{
						"type": "vcs",
						"url": "https://github.com/PackageKit/PackageKit",
					}
				],
			},
			{
				"type": "application",
				"bom-ref": "pkg:nix/nix",
				"name": "nix",
				"description": "Nix package manager",
				"licenses": [{"license": {"id": "LGPL-2.1-or-later"}}],
				"externalReferences": [
					{
						"type": "vcs",
						"url": "https://github.com/NixOS/nix",
					},
					{
						"type": "website",
						"url": "https://nixos.org",
					},
				],
			},
			{
				"type": "application",
				"bom-ref": "pkg:nix/nix-search-cli",
				"name": "nix-search-cli",
				"description": "CLI tool for searching packages via search.nixos.org",
				"licenses": [{"license": {"id": "GPL-3.0-or-later"}}],
				"externalReferences": [
					{
						"type": "vcs",
						"url": "https://github.com/peterldowns/nix-search-cli",
					}
				],
			},
			{
				"type": "library",
				"bom-ref": "pkg:nix/glib",
				"name": "glib",
				"description": "GLib C utility library",
				"licenses": [{"license": {"id": "LGPL-2.1-or-later"}}],
				"externalReferences": [
					{
						"type": "website",
						"url": "https://gitlab.gnome.org/GNOME/glib",
					}
				],
			},
			{
				"type": "library",
				"bom-ref": "pkg:nix/pkg-config",
				"name": "pkg-config",
				"description": "Tool for managing library compile and link flags",
				"licenses": [{"license": {"id": "GPL-2.0-or-later"}}],
				"externalReferences": [
					{
						"type": "website",
						"url": "https://www.freedesktop.org/wiki/Software/pkg-config/",
					}
				],
			},
		],
		"dependencies": [
			{
				"ref": "pkg:github/Avunu/nix-profile-packagekit-backend@1.0.0",
				"dependsOn": [
					"pkg:pypi/packagekit",
					"pkg:nix/nix",
					"pkg:nix/nix-search-cli",
					"pkg:nix/glib",
					"pkg:nix/pkg-config",
				],
			},
		],
	}

	return sbom


def main() -> int:
	"""Generate and save SBOM."""
	project_root = Path(__file__).parent
	output_file = project_root / "sbom.json"

	print("Generating CycloneDX SBOM...")

	sbom = create_sbom()

	# Write SBOM to file
	with open(output_file, "w") as f:
		json.dump(sbom, f, indent=2)
		f.write("\n")

	print(f"✓ SBOM generated successfully: {output_file}")
	print(f"  Format: CycloneDX {sbom['specVersion']}")
	print(f"  Components: {len(sbom['components'])}")
	print(f"  Timestamp: {sbom['metadata']['timestamp']}")

	return 0


if __name__ == "__main__":
	sys.exit(main())
