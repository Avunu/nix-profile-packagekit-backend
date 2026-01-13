# PackageKit Nix Profile Backend

A PackageKit backend that enables **GNOME Software**, **KDE Discover**, and other PackageKit-compatible software centers to manage packages in your Nix user profile.

## Features

- **Browse & Install** packages from nixpkgs through your favorite software center
- **User-level operations** - no root required, all changes go to `~/.nix-profile`
- **Always fresh data** - uses native `nix search` at runtime, no stale caches
- **Modern Nix** - uses `nix profile` commands (Nix 2.4+)

## Installation

### NixOS Flake

Add to your `flake.nix`:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nix-profile-backend.url = "github:Avunu/nix-profile-packagekit-backend";
  };

  outputs = { nixpkgs, nix-profile-backend, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        nix-profile-backend.nixosModules.default
        {
          services.packagekit.backends.nix-profile.enable = true;
          
          # Optional: Enable AppStream data for rich app listings
          # This enables app icons, descriptions, and screenshots in GNOME Software
          services.packagekit.backends.nix-profile.appstream.enable = true;
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

### Avoiding Rebuild Cascades

By default, the module uses systemd bind mounts to inject the backend at runtime,
avoiding rebuilds of packages that depend on PackageKit (like Dolphin, KWin, Plasma).

If you prefer cleaner integration at the cost of rebuilding those packages:

```nix
# Use nixosModules.full instead of nixosModules.default
nix-profile-backend.nixosModules.full

# Or explicitly disable avoidRebuilds:
services.packagekit.backends.nix-profile.avoidRebuilds = false;
```

### Manual Testing

```bash
# Build the backend
nix build

# Test the Python backend directly
printf 'get-packages\tinstalled\n' | result/share/PackageKit/helpers/nix-profile/nix_profile_backend.py
```

## How It Works

This backend follows PackageKit's **spawned backend** architecture:

1. **C Shim** (`libpk_backend_nix-profile.so`) - Loaded by PackageKit daemon
2. **Python Backend** (`nix_profile_backend.py`) - Spawned for each operation

Package operations map to `nix` commands:
- `install-packages` → `nix profile install nixpkgs#<package>`
- `remove-packages` → `nix profile remove <index>`
- `get-packages` → Parses `~/.nix-profile/manifest.json`
- `search-*` → `nix search nixpkgs <term> --json`

## Architecture

```
┌─────────────────────┐
│   GNOME Software    │
│   KDE Discover      │
└─────────┬───────────┘
          │ D-Bus
┌─────────▼───────────┐
│  PackageKit Daemon  │
└─────────┬───────────┘
          │ dlopen
┌─────────▼───────────┐
│ libpk_backend_      │
│ nix-profile.so      │  (C shim)
└─────────┬───────────┘
          │ spawn
┌─────────▼───────────┐
│ nix_profile_        │
│ backend.py          │  (Python backend)
└─────────┬───────────┘
          │ subprocess
┌─────────▼───────────┐
│  nix profile        │
│  nix search         │
│  nix eval           │
└─────────────────────┘
```

## Requirements

- NixOS or Nix with flakes enabled
- PackageKit (automatically satisfied on most desktop NixOS configs)
- A PackageKit client (GNOME Software, KDE Discover, etc.)

## Limitations

- **Search speed**: Uses `nix-search-cli` for fast searches via search.nixos.org
- **Dependencies**: Nix profile doesn't expose dependency information to PackageKit
- **System packages**: Only manages user profile, not NixOS system configuration
- **Categories**: Category browsing is limited (nix doesn't have native categories)
- **AppStream data**: Pre-generated data may be outdated; consider regenerating periodically

## AppStream Data

For GNOME Software and KDE Discover to show app icons, descriptions, and screenshots,
you need AppStream metadata. Enable it with:

```nix
services.packagekit.backends.nix-profile.appstream.enable = true;
```

This flake includes pre-generated data from
[snowfallorg/nixos-appstream-data](https://github.com/snowfallorg/nixos-appstream-data).
The module automatically creates symlinks in `/usr/share/swcatalog/` for 
AppStream 1.0+ compatibility.

**Note**: The bundled AppStream data may be outdated. For fresh data, you can:

1. Use the [nixos-appstream-generator](https://github.com/snowfallorg/nixos-appstream-generator) 
   to regenerate against current nixpkgs
2. Point `appstream.package` to your own package with AppStream XML files

## Configuration Options

```nix
services.packagekit.backends.nix-profile = {
  # Enable the nix-profile PackageKit backend
  enable = true;

  appstream = {
    # Enable AppStream data for rich app listings in GNOME Software/Discover
    enable = true;

    # Override the AppStream data package (default: pkgs.nixos-appstream-data from this flake)
    # package = pkgs.my-custom-appstream-data;
  };
};
```

## Development

```bash
# Enter dev shell
nix develop

# Run unit tests
pytest tests/ -v

# Run all checks (unit tests + NixOS VM integration test)
nix flake check

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
- Inspired by PackageKit's pisi backend architecture
