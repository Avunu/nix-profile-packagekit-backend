# PackageKit Nix Profile Backend - Quick Reference

## Installation

```nix
# flake.nix
{
  inputs.packagekit-nix-profile.url = "github:yourusername/packagekit-nix-profile";
  
  outputs = { packagekit-nix-profile, ... }: {
    nixosConfigurations.myhost = {
      modules = [
        packagekit-nix-profile.nixosModules.default
        { services.packagekit.backends.nix-profile.enable = true; }
      ];
    };
  };
}
```

```bash
sudo nixos-rebuild switch --flake .#myhost
```

## Basic Commands

| Action | Command | Example |
|--------|---------|---------|
| Search packages | `pkcon search name <query>` | `pkcon search name firefox` |
| Get details | `pkcon get-details <package>` | `pkcon get-details firefox` |
| Install package | `pkcon install <package>` | `pkcon install firefox` |
| Remove package | `pkcon remove <package>` | `pkcon remove firefox` |
| List installed | `pkcon get-packages --filter installed` | `pkcon get-packages --filter installed` |
| Check updates | `pkcon get-updates` | `pkcon get-updates` |
| Update package | `pkcon update <package>` | `pkcon update firefox` |
| Update all | `pkcon update` | `pkcon update` |
| Search category | `pkcon get-categories` | `pkcon get-categories` |

## Configuration

### Minimal

```nix
services.packagekit.backends.nix-profile.enable = true;
```

### With Channel

```nix
services.packagekit.backends.nix-profile = {
  enable = true;
  defaultChannel = "nixos-24.05";  # or "nixos-unstable"
};
```

### Full Options

```nix
services.packagekit.backends.nix-profile = {
  enable = true;
  defaultChannel = "nixos-unstable";
  autoDetectChannel = true;
  cacheDir = "/var/cache/packagekit-nix-profile";
  cacheExpiry = 3600;  # seconds
  maxSearchResults = 1000;
  enableCategories = true;
  enableAppStream = true;
};
```

## Desktop Integration

### GNOME Software

Works automatically after installation. Open GNOME Software and:
- Browse categories
- Search for applications
- Click "Install" on any package
- View screenshots and rich metadata

### KDE Discover

Works automatically after installation. Open Discover and:
- Browse "Applications" section
- Search and filter
- Install with one click
- Manage installed packages

## Troubleshooting

### Backend not found

```bash
pkcon backend-details
systemctl restart packagekit
```

### No search results

```bash
ls -l /var/lib/PackageKit/backends/nix-data-db
systemctl restart packagekit
```

### Permission errors

```bash
# Ensure user has nix profile
nix profile list

# Initialize if needed
nix profile install nixpkgs#hello
```

### Check logs

```bash
journalctl -u packagekit -f
```

## Features

- ✅ Browse nixpkgs packages
- ✅ Install to user profile (no root)
- ✅ Remove packages
- ✅ Update packages
- ✅ Search by name/description
- ✅ Category browsing
- ✅ Rich metadata (icons, screenshots)
- ✅ Progress reporting
- ✅ Desktop integration
- ❌ System package management (use nixos-rebuild)
- ❌ Configuration.nix editing (use editor)

## Data Sources

- **nix-data-db**: Fast SQLite databases with package metadata
- **nixos-appstream-data**: AppStream XML with categories, icons, screenshots
- Both from [snowfallorg](https://github.com/snowfallorg)

## Files & Locations

- Backend: `/var/lib/PackageKit/backends/nix-profile`
- Config: `/etc/PackageKit/nix-profile.conf`
- Cache: `/var/cache/packagekit-nix-profile`
- User profile: `~/.nix-profile/`
- Manifest: `~/.nix-profile/manifest.json`

## Development

```bash
# Clone
git clone https://github.com/yourusername/packagekit-nix-profile
cd packagekit-nix-profile

# Enter dev shell
nix develop

# Install deps
uv sync

# Run tests
uv run pytest

# Format code
uv run black .
```

## Links

- **Source**: https://github.com/yourusername/packagekit-nix-profile
- **Issues**: https://github.com/yourusername/packagekit-nix-profile/issues
- **Data DB**: https://github.com/snowfallorg/nix-data-db
- **AppStream**: https://github.com/snowfallorg/nixos-appstream-data
- **PackageKit**: https://www.freedesktop.org/software/PackageKit/

## Support

- User profile operations only
- No root/sudo required
- Works with Nix 2.4+
- NixOS or Nix on Linux
- Compatible with GNOME/KDE software centers

## License

GPL-2.0-or-later

---

For detailed information, see:
- [README.md](README.md) - Full documentation
- [DEPLOYMENT.md](DEPLOYMENT.md) - Installation guide
- [QUICKSTART.md](QUICKSTART.md) - Usage examples
- [TESTING.md](TESTING.md) - Testing guide
