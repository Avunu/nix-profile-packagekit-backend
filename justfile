# AppStream generation commands
# Run with: just <command>

# Default: show available commands
default:
    @just --list

# Run all tests
test:
    python -m pytest tests/ --ignore=tests/test_sbom.py -v

# Run E2E integration tests only
test-e2e:
    python -m pytest tests/test_e2e_integration.py -v -s

# Run E2E tests excluding slow tests that require authentication
test-e2e-fast:
    python -m pytest tests/test_e2e_integration.py -v -m "not slow"

# Run unit tests only (no E2E)
test-unit:
    python -m pytest tests/ --ignore=tests/test_sbom.py --ignore=tests/test_e2e_integration.py -v

# Run a specific test by name pattern
test-match pattern:
    python -m pytest tests/ --ignore=tests/test_sbom.py -v -k "{{pattern}}"

# Refresh nixpkgs-apps.json from local nixpkgs store
refresh:
    python appstream.py refresh --output ./nixpkgs-apps.json

# Refresh from a specific nixpkgs path
refresh-from path:
    python appstream.py refresh --output ./nixpkgs-apps.json --nixpkgs {{path}}

# Test correlation for a specific Flathub ID
match id:
    python appstream.py match {{id}}

# Look up info about a nixpkgs package
info package:
    python appstream.py info {{package}}

# Run full correlation analysis and generate report
correlate:
    python appstream.py correlate --report ./correlation-report.json

# Generate AppStream catalog (downloads icons, creates XML)
generate:
    python appstream.py generate --output ./appstream-data

# Generate without downloading icons
generate-no-icons:
    python appstream.py generate --output ./appstream-data --no-icons
