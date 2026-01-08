# Integration Guide - Adding Nix Profile Backend to PackageKit Build

## Overview

This guide explains how to integrate the nix-profile backend into the PackageKit build system.

## Backend Location

The backend is located at:
```
PackageKit/backends/nix-profile/
```

This is separate from the existing C++ nix backend at `PackageKit/backends/nix/`

## Build System Integration

### Current Status

✅ Backend code complete  
✅ Meson build file created  
✅ Configuration file ready  
⏳ Needs to be enabled in meson_options.txt  

### Option 1: Automatic Detection (Recommended)

The backend will be automatically built if you enable it in the packaging_backend option.

From PackageKit root directory:

```bash
# Configure with nix-profile backend
meson setup build -Dpackaging_backend=nix-profile

# Or add to existing backends
meson setup build -Dpackaging_backend=apt,nix-profile
```

### Option 2: Add to Default Backends

Edit `PackageKit/meson_options.txt`:

```meson
option('packaging_backend',
  type: 'array',
  choices: [
    'alpm',
    'apt',
    'aptcc',
    'dnf',
    'dummy',
    'entropy',
    'nix',
    'nix-profile',  # ← ADD THIS LINE
    # ... other backends
  ],
  value: [],
  description: 'packaging backend to use'
)
```

## Installation Paths

When built, files are installed to:

```
/usr/libexec/packagekit-backend/
├── nixProfileBackend.py
├── nix_profile.py
└── nixpkgs_appdata.py

/etc/PackageKit/
└── nix-profile.conf
```

## Verifying Installation

After building and installing:

```bash
# Check backend is available
pkcon backend-details

# Should show nix-profile in the list

# Check files are installed
ls -l /usr/libexec/packagekit-backend/nix*

# Test the backend
cd PackageKit/backends/nix-profile
./test_backend.py
```

## Configuration

### System-wide Configuration

Edit `/etc/PackageKit/nix-profile.conf`:

```ini
[Backend]
Description=Nix Profile Package Manager
RequiresRoot=false

[Cache]
MaxCacheAge=86400

[Appdata]
AppdataRepo=https://github.com/snowfallorg/nix-software-center
AutoDownload=true
```

### User-level Configuration

Users can set environment variables:

```bash
# Custom cache directory
export PACKAGEKIT_NIX_CACHE=$HOME/.local/share/pk-nix-cache

# Custom appdata URL (advanced)
export PACKAGEKIT_NIX_APPDATA_URL=https://custom.url/appdata.yml.gz
```

## Backend Registration

PackageKit automatically detects backends in `/usr/libexec/packagekit-backend/`.

The backend name is determined by the filename: `nixProfileBackend.py` → `nix-profile`

## Coexistence with C++ Nix Backend

The Python `nix-profile` backend can coexist with the C++ `nix` backend:

- **nix**: System-wide package management (C++)
- **nix-profile**: User profile management (Python)

They serve different use cases and don't conflict.

## Testing Integration

### Unit Tests (Future)

```bash
# Run backend unit tests
meson test -C build nix-profile
```

### Integration Tests

```bash
# Test with pkcon
pkcon search name firefox
pkcon install firefox
pkcon remove firefox

# Test with software centers
gnome-software
# or
plasma-discover
```

## Troubleshooting Build Issues

### Issue: Backend not found after build

**Solution**: Check meson configuration
```bash
meson configure build | grep packaging_backend
```

### Issue: Python import errors

**Solution**: Ensure PackageKit Python modules are installed
```bash
python3 -c "import packagekit; print(packagekit.__file__)"
```

### Issue: Permission denied

**Solution**: Install with sudo
```bash
sudo ninja -C build install
```

## Distribution-Specific Notes

### NixOS

For NixOS systems, the backend should be packaged as a Nix derivation:

```nix
# pkgs/tools/package-management/packagekit-nix-profile/default.nix
{ lib, python3Packages, packagekit, ... }:

python3Packages.buildPythonApplication {
  pname = "packagekit-nix-profile";
  version = "1.0.0-alpha";
  
  src = ./backends/nix-profile;
  
  propagatedBuildInputs = with python3Packages; [
    pyyaml
    packagekit
  ];
  
  # ... rest of derivation
}
```

### Arch Linux

For Arch-based systems:

```bash
# PKGBUILD
pkgname=packagekit-nix-profile
pkgver=1.0.0
# ...
depends=('packagekit' 'python' 'python-yaml' 'nix')
```

### Debian/Ubuntu

For Debian-based systems:

```bash
# debian/control
Package: packagekit-nix-profile
Depends: packagekit, python3, python3-yaml, nix-bin
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Build and Test

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: cachix/install-nix-action@v18
      
      - name: Install dependencies
        run: |
          sudo apt-get install -y meson ninja-build packagekit
          pip3 install pyyaml
      
      - name: Build
        run: |
          meson setup build -Dpackaging_backend=nix-profile
          ninja -C build
      
      - name: Test
        run: |
          cd backends/nix-profile
          python3 test_backend.py
```

## Release Process

When ready to release:

1. **Update version numbers**
   - CHANGELOG.md
   - SUMMARY.md
   - Backend code

2. **Tag the release**
   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```

3. **Build distribution packages**
   ```bash
   meson setup build -Dpackaging_backend=nix-profile
   ninja -C build dist
   ```

4. **Upload to releases**
   - GitHub releases
   - Distribution repositories

## Maintenance

### Updating Appdata Integration

When snowfallorg/nix-software-center releases new appdata formats:

1. Update `nixpkgs_appdata.py`
2. Adjust database schema if needed
3. Test with new appdata
4. Increment version number

### Updating for New Nix Versions

When Nix changes `nix profile` behavior:

1. Test with new Nix version
2. Update `nixProfileBackend.py` if needed
3. Update manifest.json parsing if format changes
4. Document changes in CHANGELOG.md

## Support Matrix

| Component | Version | Status |
|-----------|---------|--------|
| Python | 3.6+ | ✅ Supported |
| Nix | 2.4+ | ✅ Required |
| PackageKit | 1.2+ | ✅ Tested |
| GNOME Software | 40+ | ⏳ Testing |
| KDE Discover | 5.20+ | ⏳ Testing |

## Getting Help

If you encounter issues integrating the backend:

1. Check the [README.md](README.md) for documentation
2. Review [QUICKSTART.md](QUICKSTART.md) for setup steps
3. Check PackageKit logs: `journalctl -u packagekit`
4. Enable debug output: `PK_BACKEND_SPAWN_DEBUG=1`
5. Open an issue (once standalone project exists)

## Contributing Integration Improvements

To contribute:

1. Test on your distribution
2. Document any required changes
3. Submit patches or PRs
4. Update this guide with your findings

---

**Last Updated**: 2025-01-01  
**Maintainer**: PackageKit Nix Backend Contributors  
**Status**: Ready for integration and testing
