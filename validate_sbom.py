#!/usr/bin/env python3
"""
Validate CycloneDX SBOM (Software Bill of Materials).

This script validates the structure and content of a CycloneDX SBOM file,
checking for required fields, proper formatting, and completeness.
"""

import json
import sys
from pathlib import Path
from typing import Any


class SBOMValidator:
	"""Validator for CycloneDX SBOM files."""

	def __init__(self, sbom_data: dict[str, Any]):
		self.sbom = sbom_data
		self.errors: list[str] = []
		self.warnings: list[str] = []

	def validate(self) -> bool:
		"""Run all validations and return True if valid."""
		self.validate_format()
		self.validate_metadata()
		self.validate_components()
		self.validate_dependencies()
		return len(self.errors) == 0

	def validate_format(self) -> None:
		"""Validate basic SBOM format."""
		if self.sbom.get("bomFormat") != "CycloneDX":
			self.errors.append("Invalid bomFormat: must be 'CycloneDX'")

		spec_version = self.sbom.get("specVersion")
		if not spec_version:
			self.errors.append("Missing specVersion field")
		elif spec_version not in ["1.4", "1.5", "1.6"]:
			self.warnings.append(f"Uncommon specVersion: {spec_version}")

		if "serialNumber" not in self.sbom:
			self.errors.append("Missing serialNumber field")

		if "version" not in self.sbom:
			self.errors.append("Missing version field")

	def validate_metadata(self) -> None:
		"""Validate metadata section."""
		metadata = self.sbom.get("metadata")
		if not metadata:
			self.errors.append("Missing metadata section")
			return

		if "timestamp" not in metadata:
			self.errors.append("Missing metadata.timestamp")

		if "component" not in metadata:
			self.errors.append("Missing metadata.component (main component)")
			return

		component = metadata["component"]
		self._validate_component_fields(component, "metadata.component")

	def validate_components(self) -> None:
		"""Validate components array."""
		components = self.sbom.get("components")
		if not components:
			self.warnings.append("No components listed (empty dependency list)")
			return

		if not isinstance(components, list):
			self.errors.append("components must be an array")
			return

		for i, component in enumerate(components):
			self._validate_component_fields(component, f"components[{i}]")

	def validate_dependencies(self) -> None:
		"""Validate dependencies array."""
		dependencies = self.sbom.get("dependencies")
		if not dependencies:
			self.warnings.append("No dependencies section")
			return

		if not isinstance(dependencies, list):
			self.errors.append("dependencies must be an array")
			return

		# Check that all component references are valid
		all_refs = {self.sbom.get("metadata", {}).get("component", {}).get("bom-ref")}
		for component in self.sbom.get("components", []):
			if "bom-ref" in component:
				all_refs.add(component["bom-ref"])

		for i, dep in enumerate(dependencies):
			if "ref" not in dep:
				self.errors.append(f"dependencies[{i}] missing 'ref' field")
			elif dep["ref"] not in all_refs:
				self.errors.append(f"dependencies[{i}] references unknown component: {dep['ref']}")

			if "dependsOn" in dep:
				for dep_ref in dep["dependsOn"]:
					if dep_ref not in all_refs:
						self.errors.append(
							f"dependencies[{i}] references unknown dependency: {dep_ref}"
						)

	def _validate_component_fields(self, component: dict[str, Any], path: str) -> None:
		"""Validate required fields in a component."""
		if "type" not in component:
			self.errors.append(f"{path}: missing 'type' field")
		elif component["type"] not in [
			"application",
			"framework",
			"library",
			"container",
			"operating-system",
			"device",
			"firmware",
			"file",
		]:
			self.warnings.append(f"{path}: unusual component type: {component['type']}")

		if "name" not in component:
			self.errors.append(f"{path}: missing 'name' field")

		if "bom-ref" not in component:
			self.errors.append(f"{path}: missing 'bom-ref' field")

		# Check license format if present
		if "licenses" in component:
			if not isinstance(component["licenses"], list):
				self.errors.append(f"{path}: licenses must be an array")

	def print_results(self) -> None:
		"""Print validation results."""
		if self.errors:
			print("❌ SBOM Validation FAILED\n")
			print("Errors:")
			for error in self.errors:
				print(f"  • {error}")
		else:
			print("✅ SBOM Validation PASSED")

		if self.warnings:
			print("\nWarnings:")
			for warning in self.warnings:
				print(f"  ⚠ {warning}")

		if not self.errors and not self.warnings:
			print("\nNo issues found. SBOM is valid and complete.")


def main() -> int:
	"""Load and validate SBOM file."""
	project_root = Path(__file__).parent
	sbom_file = project_root / "sbom.json"

	if not sbom_file.exists():
		print(f"❌ Error: SBOM file not found: {sbom_file}")
		print("\nGenerate SBOM first with: ./generate-sbom.py")
		return 1

	print(f"Validating SBOM: {sbom_file}\n")

	try:
		with open(sbom_file) as f:
			sbom_data = json.load(f)
	except json.JSONDecodeError as e:
		print(f"❌ Error: Invalid JSON in SBOM file: {e}")
		return 1
	except Exception as e:
		print(f"❌ Error reading SBOM file: {e}")
		return 1

	validator = SBOMValidator(sbom_data)
	is_valid = validator.validate()
	validator.print_results()

	# Print summary stats
	print("\nSBOM Summary:")
	print(f"  Format: {sbom_data.get('bomFormat')} {sbom_data.get('specVersion')}")
	print(f"  Components: {len(sbom_data.get('components', []))}")
	print(f"  Dependencies: {len(sbom_data.get('dependencies', []))}")

	if metadata := sbom_data.get("metadata"):
		if timestamp := metadata.get("timestamp"):
			print(f"  Generated: {timestamp}")
		if component := metadata.get("component"):
			print(f"  Main Component: {component.get('name')} v{component.get('version')}")

	return 0 if is_valid else 1


if __name__ == "__main__":
	sys.exit(main())
