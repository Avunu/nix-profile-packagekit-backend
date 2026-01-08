# PackageKit Nix Profile Backend

A **standalone**, Python-based PackageKit backend for managing Nix user profile packages via `nix profile` commands. Designed for **flake-based deployment** with a dedicated NixOS module.

## Overview

This backend enables software centers (GNOME Software, Discover, KDE, etc.) to:

- **Browse** available packages in nixpkgs with full metadata
- **Install** packages to the user's nix profile
- **Remove** packages from the user's nix profile  
- **Update** packages (individual or all)
- **Search** packages by name, description, or category
- **Display** rich metadata via appdata streams (icons, descriptions, screenshots, etc.)

## Key Features

### User-Focused

- **No root required**: All operations work on the user's profile (`~/.nix-profile`)
- **No system interference**: Does NOT manage system packages, nix-env, or NixOS configuration
- **Safe**: Changes are isolated to the current user

### Rich Metadata

- Integrates with [snowfallorg/nix-data-db](https://github.com/snowfallorg/nix-data-db) for package data
- Uses pre-built SQLite databases with package metadata
- Provides descriptions, licenses, homepages
- Future: AppStream XML integration from [nixos-appstream-data](https://github.com/snowfallorg/nixos-appstream-data) for icons/screenshots

### Modern Nix Integration

- Uses `nix profile` commands (Nix 2.4+)
- Parses `--log-format internal-json` for progress tracking
- Reads `~/.nix-profile/manifest.json` for installed packages

## Architecture

### Components

1. **nixProfileBackend.py**: Main PackageKit backend implementation
   - Implements all PackageKit backend methods
   - Handles nix command execution
   - Parses JSON logs for progress tracking

2. **nix_profile.py**: Nix profile management
   - Parses `~/.nix-profile/manifest.json`
   - Maps store paths to package names/versions
   - Finds package indices for operations

3. **nixpkgs_appdata.py**: Package data integration
   - Downloads pre-built databases from nix-data-db
   - Decompresses brotli-compressed databases
   - Provides package metadata (descriptions, licenses, homepages)
   - Future: Parse AppStream XML from nixos-appstream-data

### Package ID Format

PackageKit package IDs follow the format: `name;version;arch;data`

For nix-profile backend:
- **name**: Package attribute name (e.g., `firefox`, `python3`)
- **version**: Package version from store path or appdata
- **arch**: Always `noarch` (nix handles architecture transparently)
- **data**: Always `nixpkgs` (source repository)

Example: `firefox;122.0;noarch;nixpkgs`

## Installation

### NixOS (Recommended)

Add this flake to your NixOS configuration:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    packagekit-nix-profile.url = "github:yourusername/packagekit-nix-profile";
  };

  outputs = { self, nixpkgs, packagekit-nix-profile, ... }: {
    nixosConfigurations.yourhost = nixpkgs.lib.nixosSystem {
      modules = [
        packagekit-nix-profile.nixosModules.default
        {
          services.packagekit.backends.nix-profile = {
            enable = true;
            defaultChannel = "nixos-unstable";  # or "nixos-24.05"
          };
        }
      ];
    };
  };
}
```

### Flake Installation

```bash
# Add to your system
sudo nixos-rebuild switch --flake .#yourhost

# Or try directly
nix profile install github:yourusername/packagekit-nix-profile
```

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/packagekit-nix-profile
cd packagekit-nix-profile

# Enter development shell
nix develop

# Install dependencies with uv
uv sync

# Run tests
uv run pytest
```

## Usage

### Command Line (pkcon)

```bash
# Search for packages
pkcon search name firefox

# Get package details
pkcon get-details firefox

# Install a package
pkcon install firefox

# List installed packages
pkcon get-packages --filter installed

# Update a package
pkcon update firefox

# Update all packages
pkcon update

# Remove a package
pkcon remove firefox

# Refresh cache (download latest appdata)
pkcon refresh
```

### GNOME Software

1. Install the backend as shown above
2. Restart GNOME Software: `killall gnome-software`
3. Open GNOME Software
4. Browse, search, and install packages as normal
5. Installed packages appear in the "Installed" section

### KDE Discover

Similar to GNOME Software - the backend is automatically detected and used.

## Configuration

Edit `/etc/PackageKit/nix-profile.conf`:

```ini
[Backend]
Description=Nix Profile Package Manager
RequiresRoot=false

[Cache]
# Refresh appdata if older than 24 hours
MaxCacheAge=86400

[Appdata]
AppdataRepo=https://github.com/snowfallorg/nix-software-center
AutoDownload=true
```

## Caching

The backend caches data in `~/.cache/packagekit-nix/`:

- `{channel}_nixpkgs.db`: SQLite database with package metadata (from nix-data-db)
- `{channel}_nixpkgs.db.br`: Brotli-compressed database (downloaded)
- `{channel}_nixpkgs.ver`: Version file for cache validation

Where `{channel}` is auto-detected (e.g., `nixos-unstable`, `nixos-23.05`).

## Limitations

### Not Supported

- **Dependency information**: Nix profile doesn't provide runtime dependencies
- **Local file installation**: Can't install `.drv` files (use `nix profile install` directly)
- **System packages**: Only manages user profile packages
- **NixOS configuration**: Doesn't modify `/etc/nixos/configuration.nix`
- **Category search**: Not yet implemented (requires AppStream XML parsing)
- **Icons/Screenshots**: Not yet implemented (requires nixos-appstream-data integration)

### Version Detection Caveats

- Version extraction from store paths is heuristic-based
- Complex package names may not parse perfectly
- Appdata may not have versions for all packages

## Development

### Testing

```bash
# Test with verbose output
PK_BACKEND_SPAWN_DEBUG=1 pkcon -v search name firefox

# Check logs
journalctl -f -u packagekit
```

### Adding Features

The backend follows PackageKit's Python backend API. Key methods to implement:

- `search_names()`: Search by package name
- `search_details()`: Search descriptions
- `search_groups()`: Search by category
- `install_packages()`: Install packages
- `remove_packages()`: Remove packages
- `update_packages()`: Update packages
- `get_details()`: Get package metadata
- `get_updates()`: Check for updates
- `refresh_cache()`: Update appdata

### Debugging

Enable debug logging in `nixProfileBackend.py`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Integration with snowfallorg

This backend uses the snowfallorg data infrastructure:

### nix-data-db

Pre-built SQLite databases with package metadata:
- Multiple channels (nixos-22.05, 22.11, 23.05, unstable, nixpkgs-unstable)
- Brotli-compressed for efficient download (~5-10MB compressed)
- Contains: package names, versions, descriptions, licenses, homepages
- Updated regularly via GitHub Actions

**Database Schema**:
```sql
CREATE TABLE packages (
    attribute TEXT,      -- Package attribute path (e.g., "firefox")
    pname TEXT,          -- Package name
    version TEXT,        -- Package version
    description TEXT,    -- Package description
    homepage TEXT,       -- Homepage URL
    license TEXT,        -- License information
    ...
);
```

### nixos-appstream-data (Future Integration)

AppStream XML files for rich application metadata:
- Organized by free/unfree packages
- Contains: icons (64x64, 128x128), screenshots, detailed descriptions
- Categories for software center integration
- Desktop file information

**Planned Features**:
- Parse XML files for detailed app information
- Download and cache icons locally
- Provide screenshot URLs
- Category-based browsing

## Future Enhancements

- [ ] Parse nixos-appstream-data XML files for detailed metadata
- [ ] Download and cache application icons
- [ ] Provide screenshot information
- [ ] Category-based package browsing
- [ ] Better license parsing and categorization

## Contributing

This backend will eventually become a standalone project. Contributions welcome!

Areas for improvement:
- Better error handling
- More robust version parsing
- Unit tests
- Integration tests with software centers
- Documentation

## License

Licensed under the GNU General Public License Version 2.

## Credits

- **PackageKit**: Package management abstraction layer
- **Nix**: Reproducible package manager  
- **snowfallorg**: nix-data-db and nixos-appstream-data infrastructure
- **PackageKit Python Backends**: Reference implementations (apt, zypp, portage)

## Support

- PackageKit documentation: https://www.freedesktop.org/software/PackageKit/
- Nix documentation: https://nixos.org/manual/nix/
- Report issues: (To be determined when standalone)

---

**Note**: This backend focuses solely on user profile management via `nix profile`. For system-wide package management on NixOS, use the existing C++ nix backend or manage packages through NixOS configuration.
