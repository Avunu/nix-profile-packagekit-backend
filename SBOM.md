# Software Bill of Materials (SBOM) Documentation

## Overview

This project includes comprehensive SBOM support following the [CycloneDX 1.5 specification](https://cyclonedx.org/specification/overview/). The SBOM provides a complete inventory of all software components, dependencies, and their associated metadata.

## What is an SBOM?

A Software Bill of Materials (SBOM) is a formal, machine-readable inventory of all the components that make up a software application. It's analogous to a list of ingredients on food packaging, providing transparency about what's included in the software.

### Why SBOMs are Important

1. **Security**: Quickly identify vulnerable components when security issues are disclosed
2. **Compliance**: Meet regulatory requirements (e.g., US Executive Order 14028)
3. **License Management**: Track and manage open-source licenses
4. **Supply Chain Transparency**: Understand your software's dependency tree
5. **Vulnerability Management**: Enable automated scanning for known vulnerabilities

## SBOM Contents

Our SBOM includes:

- **Main Component**: packagekit-backend-nix-profile v1.0.0
- **Dependencies**:
  - PackageKit Python bindings (GPL-2.0-or-later)
  - Nix package manager (LGPL-2.1-or-later)
  - nix-search-cli (GPL-3.0-or-later)
  - GLib C library (LGPL-2.1-or-later)
  - pkg-config (GPL-2.0-or-later)
- **Metadata**:
  - License information for each component
  - VCS (Version Control System) references
  - External references (websites, issue trackers)
  - Git commit hash of the current build
  - Dependency relationships

## Quick Start

### Using the Management Script (Recommended)

```bash
# Generate SBOM
./sbom.sh generate

# Validate SBOM
./sbom.sh validate

# Update and validate (recommended workflow)
./sbom.sh update

# Show help
./sbom.sh help
```

### Manual Usage

```bash
# Generate SBOM
python3 generate_sbom.py

# Validate SBOM
python3 validate_sbom.py
```

## File Structure

```
.
├── generate_sbom.py    # SBOM generation script
├── validate_sbom.py    # SBOM validation script
├── sbom.sh             # Management script (wrapper)
├── sbom.json           # Generated SBOM (CycloneDX 1.5)
└── tests/test_sbom.py  # Test suite
```

## CycloneDX Format

We use CycloneDX 1.5 format because it:

- **Security-Focused**: Designed specifically for security use cases
- **Lightweight**: Optimized for automation and CI/CD pipelines
- **Well-Supported**: Compatible with major security scanning tools
- **OWASP Standard**: Industry-standard format maintained by OWASP

### SBOM Structure

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "serialNumber": "urn:uuid:...",
  "version": 1,
  "metadata": {
    "timestamp": "2026-01-19T12:55:19Z",
    "component": { /* main component */ }
  },
  "components": [ /* dependencies */ ],
  "dependencies": [ /* dependency relationships */ ]
}
```

## Validation

The validator checks:

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

## Integration with Nix

### Build Integration

Generate SBOM as part of the Nix build:

```bash
# Build SBOM package
nix build .#sbom

# Check output
cat result/sbom.json
```

### Automated Checks

SBOM validation is included in `nix flake check`:

```bash
nix flake check
```

This runs:
- Unit tests
- SBOM generation
- SBOM validation
- Integration tests

## Testing

Comprehensive test suite covers:

1. **Generation Tests**: Verify SBOM structure and content
2. **Validation Tests**: Test validator logic and error handling
3. **Script Tests**: Ensure scripts run correctly
4. **Format Tests**: Validate JSON formatting

Run tests:

```bash
# Run all SBOM tests
pytest tests/test_sbom.py -v

# Run specific test class
pytest tests/test_sbom.py::TestSBOMGeneration -v
```

## CI/CD Integration

### GitHub Actions Example

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

Use SBOM with vulnerability scanners:

```bash
# Example with Grype
grype sbom:sbom.json

# Example with Trivy
trivy sbom sbom.json
```

### License Compliance

Extract license information:

```bash
# Using jq
jq '.components[] | {name, licenses}' sbom.json
```

### Dependency Analysis

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
