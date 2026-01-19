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

### How It Works

This project generates AppStream metadata by **intelligently correlating nixpkgs with Flathub** - no package building required!

**Correlation Strategy:**
1. **pname matching**: nixpkgs `pname` matches the last part of Flathub ID (e.g., `firefox` ↔ `org.mozilla.firefox`)
2. **Homepage domain matching**: Extract domain from nixpkgs `homepage` and match to Flathub ID (e.g., `mozilla.com` ↔ `org.mozilla.*`)
3. **Git platform handling**: Special logic for GitHub/GitLab URLs where username is part of Flathub ID (e.g., `github.com/alainm23/planify` ↔ `io.github.alainm23.planify`)
4. **Known mappings**: Manual fallback for edge cases

This approach:
- **Queries nix-search** (ElasticSearch) for package metadata - instant results
- **Downloads Flathub AppStream XML** - rich metadata with screenshots
- **Correlates purely via metadata** - no building, no store paths
- **Achieves ~98% coverage** for popular GUI apps

### CLI Commands

```bash
# Generate full AppStream catalog
nix-appstream generate --output ./my-appstream-data

# Look up a nixpkgs package
nix-appstream info firefox

# Test correlation for a specific Flathub ID
nix-appstream match org.mozilla.firefox

# Generate correlation report only
nix-appstream correlate --report ./report.json
```

### Adding Custom Mappings

For apps that don't auto-correlate, add manual mappings in `known-mappings.json`:

```json
{
  "com.example.MyApp": "my-nixpkgs-attr"
}
```

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

## Software Bill of Materials (SBOM)

This project uses [bombon](https://github.com/nikstur/bombon), a Nix-native tool for generating CycloneDX Software Bills of Materials. The SBOM provides a complete inventory of all components and their dependencies directly from the Nix store.

### Why bombon?

- **Nix-native**: Directly queries Nix derivations for accurate dependency information
- **Complete dependency tracking**: Automatically captures all runtime and build-time dependencies
- **Standards compliance**: Meets TR-03183 v2.0.0 (BSI) and US Executive Order 14028
- **CycloneDX format**: Industry-standard SBOM format compatible with security scanners

### Generating SBOM

Using Nix (recommended):

```bash
# Generate SBOM for the backend package
nix build .#sbom

# View the generated SBOM
cat result/bom.json
```

The SBOM includes:
- Complete dependency closure from Nix store
- Package metadata and versions
- License information
- Component relationships
- Cryptographic hashes

### Validating SBOM

To validate the SBOM structure and integrity:

### Validating SBOM

Validation is integrated into the Nix build checks:

```bash
# Run all checks including SBOM validation
nix flake check
```

For manual validation, you can use standard JSON tools:

```bash
# Validate JSON structure
jq empty result/bom.json

# Extract component information
jq '.components[] | {name, version, type}' result/bom.json

# List all licenses
jq '.components[].licenses' result/bom.json
```

### SBOM Format

The SBOM follows the [CycloneDX 1.5 specification](https://cyclonedx.org/specification/overview/), which is:
- An OWASP standard for software bill of materials
- Focused on security use cases and vulnerability management
- Machine-readable JSON format
- Widely supported by security scanning tools (Grype, Trivy, etc.)

### Using the SBOM

Scan for vulnerabilities:

```bash
# Using Grype
grype sbom:result/bom.json

# Using Trivy
trivy sbom result/bom.json
```

### Legacy Python Scripts

For backwards compatibility, Python scripts for basic SBOM generation are included:

```bash
# Generate basic SBOM (manual dependencies only)
python3 generate_sbom.py

# Validate generated SBOM
python3 validate_sbom.py
```

**Note**: The Nix-native bombon approach is recommended as it provides complete and accurate dependency information directly from the Nix store.

## License

GPL-2.0-or-later (matching PackageKit)

## Credits

- [PackageKit](https://github.com/PackageKit/PackageKit) - The package management abstraction layer
- Inspired by PackageKit's pisi backend architecture
