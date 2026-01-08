# Testing Guide

This guide covers testing the PackageKit Nix Profile backend.

## Quick Test

```bash
# Enter development environment
nix develop

# Install dependencies
uv sync

# Run basic tests
uv run pytest

# Test backend directly
python nixProfileBackend.py
```

## Unit Tests

### Running Tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/test_nix_profile.py

# Specific test
uv run pytest tests/test_nix_profile.py::test_parse_manifest

# With coverage
uv run pytest --cov=. --cov-report=html

# Verbose output
uv run pytest -v
```

### Test Structure

```
tests/
├── test_nix_profile.py          # Tests for nix_profile.py
├── test_nixpkgs_appdata.py      # Tests for nixpkgs_appdata.py
├── test_appstream_parser.py     # Tests for appstream_parser.py
├── test_backend.py              # Tests for nixProfileBackend.py
└── fixtures/
    ├── manifest.json            # Sample manifest files
    ├── sample.db                # Sample database
    └── appstream/               # Sample AppStream XML
```

## Integration Tests

### Manual Backend Testing

Test the backend standalone:

```bash
# Create test manifest
mkdir -p ~/.nix-profile
cat > ~/.nix-profile/manifest.json << 'EOF'
{
  "version": 2,
  "elements": [
    {
      "attrPath": "firefox",
      "storePaths": ["/nix/store/xxx-firefox-122.0"],
      "url": "flake:nixpkgs"
    }
  ]
}
EOF

# Test backend methods
python -c "
from nixProfileBackend import PackageKitNixProfileBackend
backend = PackageKitNixProfileBackend()
# Test get_packages
backend.get_packages('installed')
"
```

### Testing with PackageKit

Test through PackageKit's pkcon:

```bash
# List backends
pkcon backend-details

# Search
pkcon search name firefox

# Get details
pkcon get-details firefox

# Install (requires proper setup)
pkcon install firefox

# List installed
pkcon get-packages --filter installed

# Remove
pkcon remove firefox
```

## Test Scenarios

### Scenario 1: Fresh Profile

Test with a new/empty Nix profile:

```bash
# Backup existing profile
mv ~/.nix-profile ~/.nix-profile.backup

# Initialize new profile
nix profile install nixpkgs#hello

# Test backend
pkcon get-packages --filter installed
# Should show: hello

# Restore
rm -rf ~/.nix-profile
mv ~/.nix-profile.backup ~/.nix-profile
```

### Scenario 2: Multiple Packages

Test with multiple installed packages:

```bash
# Install several packages
nix profile install nixpkgs#hello
nix profile install nixpkgs#htop
nix profile install nixpkgs#jq

# List via backend
pkcon get-packages --filter installed
# Should show: hello, htop, jq

# Clean up
nix profile remove hello htop jq
```

### Scenario 3: Search and Install

Full workflow test:

```bash
# Search
pkcon search name ripgrep

# Get details
pkcon get-details ripgrep

# Install
pkcon install ripgrep

# Verify
which rg
rg --version

# Remove
pkcon remove ripgrep
```

### Scenario 4: Categories

Test category browsing (requires AppStream):

```bash
# Get categories
pkcon get-categories

# Search in category
pkcon search category "Development;IDE"

# Should show: vscode, emacs, vim, etc.
```

### Scenario 5: Updates

Test update functionality:

```bash
# List updates
pkcon get-updates

# Update single package
pkcon update firefox

# Update all
pkcon update
```

## Mocking and Test Data

### Mock Nix Commands

For testing without actual Nix:

```python
# In test files
from unittest.mock import patch, Mock

def test_install_package():
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"level":"info","action":"completed"}\n'
        )
        
        backend = PackageKitNixProfileBackend()
        backend.install_packages(['firefox'])
        
        mock_run.assert_called_once()
```

### Sample Data

Create fixtures for testing:

```python
# tests/fixtures/sample_manifest.py
SAMPLE_MANIFEST = {
    "version": 2,
    "elements": [
        {
            "attrPath": "hello",
            "storePaths": ["/nix/store/abc-hello-2.12"],
            "url": "flake:nixpkgs"
        }
    ]
}

# tests/fixtures/sample_db.py
# Create SQLite database with test data
import sqlite3

def create_test_db(path):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE packages (
            attribute TEXT PRIMARY KEY,
            pname TEXT,
            version TEXT,
            description TEXT
        )
    ''')
    
    cursor.execute('''
        INSERT INTO packages VALUES
        ('firefox', 'firefox', '122.0', 'Web browser'),
        ('hello', 'hello', '2.12', 'Hello world program')
    ''')
    
    conn.commit()
    conn.close()
```

## Performance Testing

### Search Performance

```bash
# Time search operations
time pkcon search name firefox
time pkcon search name "text editor"

# Should complete in < 2 seconds for most queries
```

### Cache Performance

```bash
# First search (cold cache)
time pkcon search name firefox

# Second search (warm cache)
time pkcon search name firefox
# Should be significantly faster
```

### Large Dataset

```bash
# Search with many results
time pkcon search name python
# Should handle 1000+ results efficiently
```

## Continuous Integration

### GitHub Actions

Example workflow:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: cachix/install-nix-action@v23
        with:
          nix_path: nixpkgs=channel:nixos-unstable
      
      - name: Build
        run: nix build
      
      - name: Run tests
        run: nix develop -c uv run pytest
      
      - name: Check formatting
        run: nix develop -c uv run black --check .
```

## Debugging Tests

### Enable Verbose Logging

```python
# In test files
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Interactive Testing

```bash
# Start Python REPL
uv run python

>>> from nixProfileBackend import PackageKitNixProfileBackend
>>> backend = PackageKitNixProfileBackend()
>>> backend.get_packages('installed')
>>> # Test methods interactively
```

### Using pdb

```python
# In code
import pdb; pdb.set_trace()

# Or with pytest
uv run pytest --pdb  # Drop into debugger on failure
```

## Known Issues

### Test Environment

- Tests require Nix to be available
- Some tests need network access for downloading databases
- PackageKit integration tests require PackageKit daemon

### Mock Limitations

- Nix commands have complex JSON output that's hard to mock completely
- Store path parsing depends on actual Nix store structure
- Some tests need real data from nix-data-db

## Contributing Tests

When adding features, please include:

1. Unit tests for new functions
2. Integration tests for new workflows
3. Documentation of test scenarios
4. Mock data for reproducibility

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.
