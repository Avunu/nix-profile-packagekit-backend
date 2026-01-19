"""Tests for SBOM generation and validation."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add parent directory to path to import the scripts
sys.path.insert(0, str(Path(__file__).parent.parent))

from generate_sbom import create_sbom  # noqa: E402
from validate_sbom import SBOMValidator  # noqa: E402


class TestSBOMGeneration:
	"""Test SBOM generation functionality."""

	def test_create_sbom_structure(self):
		"""Test that create_sbom returns valid structure."""
		sbom = create_sbom()

		# Check required top-level fields
		assert sbom["bomFormat"] == "CycloneDX"
		assert sbom["specVersion"] == "1.5"
		assert "serialNumber" in sbom
		assert "version" in sbom
		assert sbom["version"] == 1

	def test_sbom_metadata(self):
		"""Test SBOM metadata section."""
		sbom = create_sbom()

		assert "metadata" in sbom
		metadata = sbom["metadata"]

		# Check timestamp
		assert "timestamp" in metadata

		# Check tools
		assert "tools" in metadata
		assert "components" in metadata["tools"]

		# Check main component
		assert "component" in metadata
		component = metadata["component"]
		assert component["name"] == "packagekit-backend-nix-profile"
		assert component["version"] == "1.0.0"
		assert component["type"] == "application"
		assert "licenses" in component
		assert component["licenses"][0]["license"]["id"] == "GPL-2.0-or-later"

	def test_sbom_components(self):
		"""Test SBOM components list."""
		sbom = create_sbom()

		assert "components" in sbom
		components = sbom["components"]

		# Check we have expected dependencies
		component_names = {c["name"] for c in components}
		expected_components = {
			"packagekit",
			"nix",
			"nix-search-cli",
			"glib",
			"pkg-config",
		}
		assert expected_components.issubset(component_names)

		# Check each component has required fields
		for component in components:
			assert "type" in component
			assert "name" in component
			assert "bom-ref" in component

	def test_sbom_dependencies(self):
		"""Test SBOM dependencies section."""
		sbom = create_sbom()

		assert "dependencies" in sbom
		dependencies = sbom["dependencies"]

		# Should have at least one dependency entry
		assert len(dependencies) > 0

		# Main component should list dependencies
		main_dep = dependencies[0]
		assert "ref" in main_dep
		assert "dependsOn" in main_dep
		assert len(main_dep["dependsOn"]) > 0

	def test_sbom_external_references(self):
		"""Test external references in components."""
		sbom = create_sbom()

		main_component = sbom["metadata"]["component"]
		assert "externalReferences" in main_component

		refs = main_component["externalReferences"]
		ref_types = {ref["type"] for ref in refs}
		assert "vcs" in ref_types
		assert "website" in ref_types
		assert "issue-tracker" in ref_types


class TestSBOMValidation:
	"""Test SBOM validation functionality."""

	def test_validator_accepts_valid_sbom(self):
		"""Test that validator accepts a valid SBOM."""
		sbom = create_sbom()
		validator = SBOMValidator(sbom)

		is_valid = validator.validate()
		assert is_valid
		assert len(validator.errors) == 0

	def test_validator_rejects_invalid_format(self):
		"""Test validator catches invalid bomFormat."""
		sbom = create_sbom()
		sbom["bomFormat"] = "Invalid"

		validator = SBOMValidator(sbom)
		is_valid = validator.validate()

		assert not is_valid
		assert len(validator.errors) > 0
		assert any("bomFormat" in error for error in validator.errors)

	def test_validator_requires_metadata(self):
		"""Test validator requires metadata section."""
		sbom = create_sbom()
		del sbom["metadata"]

		validator = SBOMValidator(sbom)
		is_valid = validator.validate()

		assert not is_valid
		assert any("metadata" in error for error in validator.errors)

	def test_validator_requires_serial_number(self):
		"""Test validator requires serialNumber."""
		sbom = create_sbom()
		del sbom["serialNumber"]

		validator = SBOMValidator(sbom)
		is_valid = validator.validate()

		assert not is_valid
		assert any("serialNumber" in error for error in validator.errors)

	def test_validator_checks_component_fields(self):
		"""Test validator checks component required fields."""
		sbom = create_sbom()
		# Remove required field from a component
		sbom["components"][0].pop("name")

		validator = SBOMValidator(sbom)
		is_valid = validator.validate()

		assert not is_valid
		assert any("name" in error for error in validator.errors)

	def test_validator_checks_dependency_refs(self):
		"""Test validator checks dependency references are valid."""
		sbom = create_sbom()
		# Add invalid dependency reference
		sbom["dependencies"][0]["dependsOn"].append("pkg:invalid/nonexistent")

		validator = SBOMValidator(sbom)
		is_valid = validator.validate()

		assert not is_valid
		assert any("unknown dependency" in error for error in validator.errors)


class TestSBOMScripts:
	"""Test SBOM generation and validation scripts."""

	def test_generate_sbom_script_runs(self, tmp_path):
		"""Test that generate_sbom.py script runs successfully."""
		script_path = Path(__file__).parent.parent / "generate_sbom.py"
		assert script_path.exists()

		# Run the script
		result = subprocess.run(
			[sys.executable, str(script_path)],
			capture_output=True,
			text=True,
			cwd=Path(__file__).parent.parent,
		)

		assert result.returncode == 0
		assert "SBOM generated successfully" in result.stdout

	def test_validate_sbom_script_runs(self):
		"""Test that validate_sbom.py script runs successfully."""
		script_path = Path(__file__).parent.parent / "validate_sbom.py"
		sbom_path = Path(__file__).parent.parent / "sbom.json"

		assert script_path.exists()

		# Ensure SBOM exists
		if not sbom_path.exists():
			pytest.skip("SBOM file not generated yet")

		# Run the script
		result = subprocess.run(
			[sys.executable, str(script_path)],
			capture_output=True,
			text=True,
			cwd=Path(__file__).parent.parent,
		)

		assert result.returncode == 0
		assert "Validation" in result.stdout

	def test_generated_sbom_is_valid_json(self):
		"""Test that generated SBOM is valid JSON."""
		sbom_path = Path(__file__).parent.parent / "sbom.json"

		if not sbom_path.exists():
			pytest.skip("SBOM file not generated yet")

		with open(sbom_path) as f:
			sbom = json.load(f)

		assert isinstance(sbom, dict)
		assert sbom["bomFormat"] == "CycloneDX"

	def test_sbom_file_format(self):
		"""Test SBOM file has proper formatting."""
		sbom_path = Path(__file__).parent.parent / "sbom.json"

		if not sbom_path.exists():
			pytest.skip("SBOM file not generated yet")

		with open(sbom_path) as f:
			content = f.read()

		# Check it's properly formatted JSON
		sbom = json.loads(content)
		# Re-serialize to check formatting
		formatted = json.dumps(sbom, indent=2)

		# Should have proper indentation
		assert "  " in content
		assert content.strip().endswith("}")
