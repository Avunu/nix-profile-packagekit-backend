# PackageKit Nix Profile Backend

A PackageKit backend that enables **GNOME Software**, **KDE Discover**, and other PackageKit-compatible software centers to manage packages in your Nix user profile.

## Features

- **Browse & Install** packages from nixpkgs through your favorite software center
- **User-level operations** - no root required, all changes go to `~/.nix-profile`
- **Rich metadata** via [snowfallorg](https://github.com/snowfallorg) AppStream data
- **Modern Nix** - uses `nix profile` commands (Nix 2.4+)

## Screenshots

*(Coming soon - GNOME Software showing nixpkgs packages)*

## Installation

### NixOS Flake

Add to your `flake.nix`:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nix-profile-backend.url = "github:YOURUSER/packagekit-nix-profile-backend";
  };

  outputs = { nixpkgs, nix-profile-backend, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        nix-profile-backend.nixosModules.default
        {
          services.packagekit-nix-profile.enable = true;
        }
      ];
    };
  };
}
```

Then rebuild:
```bash
sudo nixos-rebuild switch
```

### Manual Testing

```bash
# Build the backend
nix build

# Test the Python backend directly
printf 'get-packages\tinstalled\n' | result/share/PackageKit/helpers/nix-profile/nixProfileBackend.py
```

## How It Works

This backend follows PackageKit's **spawned backend** architecture:

1. **C Shim** (`libpk_backend_nix-profile.so`) - Loaded by PackageKit daemon
2. **Python Backend** (`nixProfileBackend.py`) - Spawned for each operation, communicates via stdin/stdout

Package operations map to `nix profile` commands:
- `install-packages` → `nix profile install nixpkgs#<package>`
- `remove-packages` → `nix profile remove <index>`
- `get-packages` → Parses `~/.nix-profile/manifest.json`
- `search-name` → Queries AppStream catalog

## Requirements

- NixOS or Nix with flakes enabled
- PackageKit (automatically satisfied on most desktop NixOS configs)
- A PackageKit client (GNOME Software, KDE Discover, etc.)

## Data Sources

This backend uses data from [snowfallorg](https://github.com/snowfallorg):

- **[nix-data-db](https://github.com/snowfallorg/nix-data-db)** - Package metadata (versions, descriptions)
- **[nixos-appstream-data](https://github.com/snowfallorg/nixos-appstream-data)** - AppStream catalog (icons, screenshots, categories)

## Limitations

- **Dependencies**: Nix profile doesn't expose dependency information to PackageKit
- **System packages**: Only manages user profile, not NixOS system configuration
- **Atomic updates**: Each install/remove is separate (use `nix profile upgrade` for atomic bulk updates)

## Development

```bash
# Enter dev shell
nix develop

# Build
nix build

# Check build output
ls -la result/lib/packagekit-backend/
ls -la result/share/PackageKit/helpers/nix-profile/
```

## License

GPL-2.0-or-later (matching PackageKit)

## Credits

- [PackageKit](https://github.com/PackageKit/PackageKit) - The package management abstraction layer
- [snowfallorg](https://github.com/snowfallorg) - Nix package metadata and AppStream data
- Inspired by PackageKit's pisi backend architecture
