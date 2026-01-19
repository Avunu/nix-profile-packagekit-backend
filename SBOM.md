# Software Bill of Materials (SBOM) Documentation

## Overview

This project uses [bombon](https://github.com/nikstur/bombon), a Nix-native tool for generating CycloneDX Software Bills of Materials (SBOMs). Bombon provides complete and accurate dependency information by querying Nix derivations directly from the Nix store.

## Why bombon?

Unlike traditional SBOM generators that parse package manifests, bombon:

1. **Nix-native Integration**: Directly queries Nix derivations for complete dependency closures
2. **Automatic Dependency Tracking**: Captures all runtime and build-time dependencies without manual specification
3. **Accurate Versioning**: Uses actual package versions from the Nix store
4. **License Information**: Extracts license metadata from Nix package definitions
5. **Standards Compliance**: Meets TR-03183 v2.0.0 (BSI) and US Executive Order 14028 requirements

## What is an SBOM?

A Software Bill of Materials (SBOM) is a formal, machine-readable inventory of all the components that make up a software application. It's analogous to a list of ingredients on food packaging, providing transparency about what's included in the software.

### Why SBOMs are Important

1. **Security**: Quickly identify vulnerable components when security issues are disclosed
2. **Compliance**: Meet regulatory requirements (e.g., US Executive Order 14028)
3. **License Management**: Track and manage open-source licenses
4. **Supply Chain Transparency**: Understand your software's dependency tree
5. **Vulnerability Management**: Enable automated scanning for known vulnerabilities

## SBOM Contents

Bombon automatically generates a comprehensive SBOM that includes:

- **Complete Dependency Closure**: All packages in the Nix derivation closure
- **Component Metadata**: Names, versions, and types for all dependencies
- **License Information**: Extracted from Nix package metadata
- **Component Relationships**: Full dependency graph
- **Cryptographic Hashes**: Store paths and content hashes for verification

The SBOM includes dependencies such as:
- PackageKit and its Python bindings
- Nix package manager
- nix-search-cli
- GLib C library
- pkg-config
- All transitive dependencies from the Nix closure

## Quick Start

### Using Nix (Recommended)

```bash
# Generate SBOM using bombon
nix build .#sbom

# View the generated SBOM
cat result/bom.json

# Validate as part of checks
nix flake check
```

### Using Legacy Python Scripts

For basic SBOM generation without Nix:

```bash
# Generate basic SBOM (manual dependencies only)
python3 generate_sbom.py

# Validate SBOM
python3 validate_sbom.py

# Or use the wrapper script
./sbom.sh update
```

**Note**: The Python scripts provide a simplified SBOM with manually specified dependencies. For complete and accurate dependency information, use the Nix-native bombon approach.

## File Structure

```
.
├── flake.nix            # Nix flake with bombon integration
├── generate_sbom.py     # Legacy Python SBOM generation script
├── validate_sbom.py     # SBOM validation script
├── sbom.sh              # Wrapper script for Python tools
├── sbom.json            # Legacy Python-generated SBOM
└── tests/test_sbom.py   # Test suite for Python scripts
```

## CycloneDX Format

Bombon generates CycloneDX 1.5 format SBOMs because:

- **Security-Focused**: Designed specifically for security use cases
- **Complete**: Captures full Nix closure, not just direct dependencies
- **Accurate**: Uses actual package data from Nix store
- **Well-Supported**: Compatible with major security scanning tools (Grype, Trivy, etc.)
- **OWASP Standard**: Industry-standard format maintained by OWASP

### SBOM Structure

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "serialNumber": "urn:uuid:...",
  "version": 1,
  "metadata": {
    "timestamp": "...",
    "component": { /* main package from Nix */ }
  },
  "components": [ /* all dependencies from Nix closure */ ],
  "dependencies": [ /* complete dependency graph */ ]
}
```

## Validation

### Nix-based Validation

Automated validation is included in `nix flake check`:

```bash
nix flake check
```

This validates:
1. **Format Compliance**: Ensures CycloneDX specification adherence
2. **JSON Structure**: Verifies valid JSON format
3. **Required Fields**: Checks for mandatory CycloneDX fields
4. **Component Count**: Reports number of dependencies found

### Manual Validation

Use standard JSON tools:

```bash
# Validate JSON
jq empty result/bom.json

# Check format
jq -r '.bomFormat' result/bom.json  # Should be "CycloneDX"

# Count components
jq '.components | length' result/bom.json
```

### Legacy Python Validation

The Python validator provides detailed checks:

1. **Format Compliance**: Ensures CycloneDX 1.5 specification adherence
2. **Required Fields**: Verifies all mandatory fields are present
3. **Component References**: Validates all component `bom-ref` values
4. **Dependency Relationships**: Ensures dependency references are valid
5. **License Information**: Checks license format when present

### Validation Output

```
✅ SBOM Validation PASSED

No issues found. SBOM is valid and complete.

SBOM Summary:
  Format: CycloneDX 1.5
  Components: 5
  Dependencies: 1
  Generated: 2026-01-19T12:55:19.166837+00:00
  Main Component: packagekit-backend-nix-profile v1.0.0
```

## Integration with Nix and Bombon

### Flake Configuration

The project's `flake.nix` includes bombon as an input:

```nix
inputs = {
  bombon = {
    url = "github:nikstur/bombon";
    inputs.nixpkgs.follows = "nixpkgs";
  };
};
```

### Build Integration

Generate SBOM as part of the Nix build:

```bash
# Build SBOM package using bombon
nix build .#sbom

# Check output (bombon generates bom.json)
cat result/bom.json

# Extract specific information
jq '.components[] | {name, version}' result/bom.json
```

### Automated Checks

SBOM validation is included in `nix flake check`:

```bash
nix flake check
```

This runs:
- Unit tests for legacy Python scripts
- SBOM generation via bombon
- SBOM validation
- Integration tests

### Custom Derivations

You can generate SBOMs for any Nix package:

```nix
bombon.lib.${system}.buildBom pkgs.yourPackage { }
```

## Testing

The test suite covers the legacy Python SBOM scripts:

```bash
# Run all SBOM tests (for Python scripts)
pytest tests/test_sbom.py -v

# Run specific test class
pytest tests/test_sbom.py::TestSBOMGeneration -v
```

**Note**: These tests validate the Python-based SBOM generation. The bombon-generated SBOMs are validated as part of `nix flake check`.

## CI/CD Integration

### GitHub Actions with Bombon

```yaml
- name: Generate SBOM using Nix
  run: nix build .#sbom

- name: Validate SBOM
  run: nix flake check

- name: Upload SBOM as Artifact
  uses: actions/upload-artifact@v3
  with:
    name: sbom
    path: result/bom.json
```

### Legacy Python Approach

```yaml
- name: Generate and Validate SBOM
  run: |
    ./sbom.sh update
    
- name: Upload SBOM as Artifact
  uses: actions/upload-artifact@v3
  with:
    name: sbom
    path: sbom.json
```

### Pre-commit Hook

Add to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: validate-sbom
      name: Validate SBOM
      entry: ./sbom.sh validate
      language: system
      pass_filenames: false
```

## SBOM Consumption

### Security Scanning

Use bombon-generated SBOMs with vulnerability scanners:

```bash
# Build SBOM first
nix build .#sbom

# Scan with Grype
grype sbom:result/bom.json

# Scan with Trivy
trivy sbom result/bom.json

# Scan with OSV-Scanner
osv-scanner --sbom result/bom.json
```

### License Compliance

Extract license information:

```bash
# List all licenses
jq '.components[] | {name, licenses}' result/bom.json

# Count by license type
jq '.components[].licenses[].license.id' result/bom.json | sort | uniq -c
```

### Dependency Analysis

Analyze dependencies from the Nix closure:

```bash
# List all components
jq '.components[].name' result/bom.json

# Show component versions
jq '.components[] | "\(.name) \(.version)"' result/bom.json

# Find specific package
jq '.components[] | select(.name | contains("glib"))' result/bom.json
```

## Bombon vs Python Scripts

| Feature | Bombon (Recommended) | Python Scripts (Legacy) |
|---------|---------------------|------------------------|
| Dependency Discovery | Automatic from Nix closure | Manual specification |
| Completeness | Complete dependency tree | Direct dependencies only |
| Accuracy | Exact from Nix store | Approximate |
| Version Information | Precise Nix versions | Manually updated |
| License Data | From Nix metadata | Manually maintained |
| Integration | Native Nix | Requires Python runtime |
| Maintenance | Automatic | Manual updates needed |

**Recommendation**: Use bombon for production SBOMs. The Python scripts are provided for environments without Nix or for understanding SBOM structure.

Analyze dependencies:

```bash
# List all components
jq '.components[].name' sbom.json

# List external references
jq '.components[].externalReferences[]' sbom.json
```

## Maintenance

### Updating the SBOM

Update SBOM when:
- Adding new dependencies
- Updating dependency versions
- Releasing new versions
- Making significant changes

```bash
./sbom.sh update
git add sbom.json
git commit -m "Update SBOM"
```

### Version Management

The SBOM includes:
- Project version in `metadata.component.version`
- Git commit hash in `metadata.component.properties`
- Generation timestamp in `metadata.timestamp`
- Serial number for unique identification

## Best Practices

1. **Regenerate Regularly**: Update SBOM with each release
2. **Validate Before Commit**: Run `./sbom.sh validate` before committing
3. **Include in CI**: Automate SBOM generation and validation
4. **Version Control**: Commit SBOM to git for traceability
5. **Security Scanning**: Integrate with vulnerability scanners
6. **Documentation**: Keep SBOM documentation up to date

## Resources

- [CycloneDX Official Site](https://cyclonedx.org/)
- [CycloneDX 1.5 Specification](https://cyclonedx.org/docs/1.5/)
- [OWASP CycloneDX](https://owasp.org/www-project-cyclonedx/)
- [NTIA Minimum Elements for SBOM](https://www.ntia.gov/report/2021/minimum-elements-software-bill-materials-sbom)
- [US Executive Order 14028](https://www.whitehouse.gov/briefing-room/presidential-actions/2021/05/12/executive-order-on-improving-the-nations-cybersecurity/)

## Troubleshooting

### SBOM Generation Fails

```bash
# Check Python version (requires 3.11+)
python3 --version

# Check git is available
which git

# Run with verbose output
python3 -v generate_sbom.py
```

### Validation Fails

```bash
# Check SBOM file exists
ls -la sbom.json

# Validate JSON syntax
jq . sbom.json

# Run validator directly
python3 validate_sbom.py
```

### Tests Fail

```bash
# Install test dependencies
pip install pytest

# Run tests with verbose output
pytest tests/test_sbom.py -v -s
```

## Support

For issues or questions:
- Open an issue: https://github.com/Avunu/nix-profile-packagekit-backend/issues
- Check existing documentation in README.md
- Review test suite for usage examples
