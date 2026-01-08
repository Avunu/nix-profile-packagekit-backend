# Quick Start Guide - Nix Profile PackageKit Backend

## Installation

### 1. Install Dependencies

```bash
# Python and brotli for database decompression
pip install --user brotli

# Or on NixOS:
nix-shell -p python3 python3Packages.brotli
```

### 2. Build and Install

From the PackageKit root directory:

```bash
# Configure with nix-profile backend enabled
meson setup build -Dpackaging_backend=nix-profile

# Build
cd build
ninja

# Install (requires root)
sudo ninja install
```

### 3. Test the Backend

```bash
# Check backend is available
pkcon backend-details

# Run test script
cd backends/nix-profile
./test_backend.py
```

## First Time Setup

### Download Package Database

The backend needs package metadata from nix-data-db:

```bash
# Download database (may take a minute, ~5-10MB)
pkcon refresh

# This downloads brotli-compressed database to:
# ~/.cache/packagekit-nix/{channel}_nixpkgs.db.br
# and decompresses it to:
# ~/.cache/packagekit-nix/{channel}_nixpkgs.db
```

## Basic Usage

### Search

```bash
# Search by name
pkcon search name firefox

# Search descriptions
pkcon search details "web browser"
```

### Install

```bash
# Install a package
pkcon install firefox

# This runs: nix profile install nixpkgs#firefox
```

### List Installed

```bash
# Show all installed packages in your profile
pkcon get-packages --filter installed
```

### Update

```bash
# Update specific package
pkcon update firefox

# Update all packages
pkcon update
```

### Remove

```bash
# Remove a package
pkcon remove firefox
```

### Get Details

```bash
# Show package details
pkcon get-details firefox
```

## Using with GNOME Software

1. Install the backend as shown above
2. Restart GNOME Software:
   ```bash
   killall gnome-software
   gnome-software
   ```
3. Browse and install packages normally
4. Installed packages appear in "Installed" section

## Using with KDE Discover

Similar to GNOME Software - restart Discover after installation:

```bash
killall plasmashell && plasmashell &
```

## Troubleshooting

### Backend Not Found

Check installation:
```bash
ls -l /usr/libexec/packagekit-backend/nixProfileBackend.py
```

### No Packages Appear

1. Refresh the cache:
   ```bash
   pkcon refresh --force
   ```

2. Check cache exists:
   ```bash
   ls -lh ~/.cache/packagekit-nix/
   ```

### Installation Fails

Check nix is available:
```bash
which nix
nix --version
```

Ensure nix profile is enabled (Nix 2.4+):
```bash
nix profile list
```

### Debugging

Enable verbose output:
```bash
PK_BACKEND_SPAWN_DEBUG=1 pkcon -v search name firefox
```

Check PackageKit logs:
```bash
journalctl -u packagekit -f
```

## Advanced Usage

### Custom Cache Directory

Set environment variable:
```bash
export PACKAGEKIT_NIX_CACHE=$HOME/.local/share/pk-nix-cache
pkcon refresh
```

### Manual Database Download

Download directly from GitHub:
```bash
cd ~/.cache/packagekit-nix

# Detect your channel first
nix registry list | grep nixpkgs

# Download for your channel (e.g., nixos-unstable)
wget https://raw.githubusercontent.com/snowfallorg/nix-data-db/main/nixos-unstable/nixpkgs.db.br

# Decompress
brotli -d nixpkgs.db.br
mv nixpkgs.db nixos-unstable_nixpkgs.db
```

### Python API

You can use the backend modules directly:

```python
from nix_profile import NixProfile
from nixpkgs_appdata import NixpkgsAppdata

# Get installed packages
profile = NixProfile()
installed = profile.get_installed_packages()
print(installed)

# Search appdata
appdata = NixpkgsAppdata()
results = appdata.search_packages(['firefox'])
print(results)
```

## Notes

- **User-level only**: This backend only manages your user profile
- **No root needed**: All operations are user-level
- **Profile isolation**: Each user has their own profile
- **Automatic updates**: Run `pkcon update` regularly

## Next Steps

- Configure automatic updates in your software center
- Browse available packages
- Install your favorite applications
- Share feedback and contribute improvements

## Getting Help

- Check the [README.md](README.md) for detailed documentation
- Review PackageKit logs for errors
- Test with the command-line tool first (`pkcon`)
- Ensure nix profile works standalone before using the backend

---

**Tip**: If you're new to nix profile, try these commands first:
```bash
# List current profile
nix profile list

# Install something
nix profile install nixpkgs#hello

# Run it
hello

# Remove it
nix profile remove 0  # (use the index from 'list')
```
