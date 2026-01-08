# Deployment Guide

This guide covers deploying the PackageKit Nix Profile backend on NixOS systems.

## Quick Start

### 1. Add to Your NixOS Configuration

Add the flake to your `flake.nix`:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    packagekit-nix-profile.url = "github:yourusername/packagekit-nix-profile";
  };

  outputs = { self, nixpkgs, packagekit-nix-profile, ... }: {
    nixosConfigurations.yourhost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        ./configuration.nix
        packagekit-nix-profile.nixosModules.default
        {
          services.packagekit.backends.nix-profile.enable = true;
        }
      ];
    };
  };
}
```

### 2. Rebuild Your System

```bash
sudo nixos-rebuild switch --flake .#yourhost
```

### 3. Verify Installation

```bash
# Check if the backend is available
pkcon backend-details nix-profile

# Test searching
pkcon search name firefox

# Test installation
pkcon install firefox
```

## Configuration Options

### Basic Configuration

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    defaultChannel = "nixos-unstable";  # or "nixos-24.05", "nixos-23.11", etc.
    autoDetectChannel = true;  # Auto-detect from system
  };
}
```

### Advanced Configuration

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    
    # Channel configuration
    defaultChannel = "nixos-24.05";
    autoDetectChannel = true;
    
    # Cache configuration
    cacheDir = "/var/cache/packagekit-nix-profile";
    cacheExpiry = 3600;  # 1 hour in seconds
    
    # Search configuration
    maxSearchResults = 1000;
    
    # Feature toggles
    enableCategories = true;
    enableAppStream = true;
    
    # Custom data sources (optional)
    nixDataDB = pkgs.nix-data-db;
    nixosAppstreamData = pkgs.nixos-appstream-data;
    
    # Custom nix command (optional)
    nixCommand = "${pkgs.nix}/bin/nix";
  };
}
```

## Integration with Desktop Environments

### GNOME Software

GNOME Software automatically detects PackageKit backends. After installation:

1. Open GNOME Software
2. Browse categories or search for packages
3. Install packages directly from the UI
4. Updates are shown in the Updates tab

Configuration for better GNOME Software experience:

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    enableCategories = true;  # Enable category browsing
    enableAppStream = true;   # Rich metadata with icons/screenshots
  };
  
  # Optional: Make GNOME Software prefer this backend
  environment.sessionVariables = {
    PACKAGEKIT_BACKEND = "nix-profile";
  };
}
```

### KDE Discover

KDE Discover also uses PackageKit. Configuration:

```nix
{
  services.packagekit.backends.nix-profile.enable = true;
  
  # KDE Plasma with Discover
  services.xserver = {
    enable = true;
    desktopManager.plasma5.enable = true;
  };
}
```

## Channel Selection

### Auto-Detection (Recommended)

The backend can auto-detect your system's channel:

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    autoDetectChannel = true;  # Reads from NIX_PATH or system.stateVersion
  };
}
```

### Manual Channel Selection

For systems where auto-detection fails or you want to use a different channel:

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    autoDetectChannel = false;
    defaultChannel = "nixos-24.05";  # Explicitly set channel
  };
}
```

### Multiple Channels

Currently, the backend supports one channel at a time. To switch:

```nix
{
  services.packagekit.backends.nix-profile.defaultChannel = "nixos-unstable";
}
```

Then rebuild your system.

## Troubleshooting

### Backend Not Detected

```bash
# Check if backend files exist
ls -l /var/lib/PackageKit/backends/nix-profile

# Check PackageKit service status
systemctl status packagekit

# Restart PackageKit
sudo systemctl restart packagekit

# Verify backend is listed
pkcon backend-details
```

### Search Returns No Results

```bash
# Check cache directory
ls -l /var/cache/packagekit-nix-profile

# Check nix-data-db availability
ls -l /var/lib/PackageKit/backends/nix-data-db

# Force cache refresh by restarting PackageKit
sudo systemctl restart packagekit
```

### Permission Errors

The backend operates on user profiles only:

```bash
# Check user's nix profile
ls -la ~/.nix-profile/

# Check manifest
cat ~/.nix-profile/manifest.json

# Ensure user has nix profile initialized
nix profile list
```

### Nix Command Not Found

```bash
# Ensure nix is available
which nix

# Check PATH
echo $PATH

# If missing, add to configuration:
environment.systemPackages = [ pkgs.nix ];
```

### Log Debugging

```bash
# Check PackageKit logs
journalctl -u packagekit -f

# Enable verbose logging
export G_MESSAGES_DEBUG=all
pkcon search name firefox

# Check backend-specific logs
tail -f /var/log/packagekit/*.log
```

## Performance Tuning

### Cache Configuration

Adjust cache expiry for your needs:

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    cacheExpiry = 7200;  # 2 hours for slower systems
    # or
    cacheExpiry = 1800;  # 30 minutes for frequent updates
  };
}
```

### Search Result Limits

Limit results for faster searches:

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    maxSearchResults = 500;  # Reduce from default 1000
  };
}
```

### Disable Features

If you don't need certain features:

```nix
{
  services.packagekit.backends.nix-profile = {
    enable = true;
    enableCategories = false;  # Disable category browsing
    enableAppStream = false;   # Disable rich metadata
  };
}
```

This improves performance but reduces functionality in software centers.

## Uninstallation

To remove the backend:

```nix
{
  services.packagekit.backends.nix-profile.enable = false;
}
```

Then rebuild:

```bash
sudo nixos-rebuild switch --flake .#yourhost
```

Clean up cache (optional):

```bash
sudo rm -rf /var/cache/packagekit-nix-profile
```

## Security Considerations

- The backend only modifies the user's profile (`~/.nix-profile`)
- No system-wide changes are made
- No root/sudo required for package operations
- Uses Nix's built-in security features (hash verification, sandboxing)
- PackageKit's PolicyKit integration controls authorization

## Next Steps

- Read [QUICKSTART.md](QUICKSTART.md) for usage examples
- Check [TODO.md](TODO.md) for planned features
- See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute
- Report issues on GitHub
