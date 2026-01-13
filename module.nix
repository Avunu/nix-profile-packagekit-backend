{
  config,
  lib,
  pkgs,
  ...
}:
with lib; let
  cfg = config.services.packagekit.backends.nix-profile;
in {
  options.services.packagekit.backends.nix-profile = {
    enable = mkEnableOption "PackageKit Nix profile backend for managing user packages";

    package = mkOption {
      type = types.package;
      default = pkgs.packagekit-backend-nix-profile;
      defaultText = literalExpression "pkgs.packagekit-backend-nix-profile";
      description = "The packagekit-nix-profile backend package";
    };

    appstream = {
      enable = mkEnableOption "AppStream metadata for nixpkgs (enables app listings in GNOME Software/KDE Discover)";

      package = mkOption {
        type = types.nullOr types.package;
        default = pkgs.nixos-appstream-data or null;
        defaultText = literalExpression "pkgs.nixos-appstream-data";
        description = ''
          AppStream data package for nixpkgs.
          Built from snowfallorg/nixos-appstream-data by default when using the flake overlay.
          Can also use custom data from nixos-appstream-generator.
          If null, uses the dataPath option if provided.
        '';
      };

      dataPath = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = ''
          Path to AppStream XML data directory containing nixpkgs metadata.
          Alternative to package option for using external/downloaded data.
        '';
      };
    };
  };

  config = mkIf cfg.enable {
    # Ensure PackageKit is enabled
    services.packagekit.enable = mkDefault true;

    # Configure PackageKit to use nix-profile backend via upstream module's settings option
    services.packagekit.settings = {
      Daemon = {
        DefaultBackend = "nix-profile";
      };
    };

    # Create activation script to link backend files
    # PackageKit searches: /var/lib/PackageKit/plugins for backend .so files
    # and /usr/share/PackageKit/helpers/<backend>/ for spawned backends
    system.activationScripts.packagekit-nix-profile = ''
      # Link backend shared library
      mkdir -p /var/lib/PackageKit/plugins
      ln -sf ${cfg.package}/lib/packagekit-backend/libpk_backend_nix-profile.so \
             /var/lib/PackageKit/plugins/

      # Link helper scripts
      mkdir -p /usr/share/PackageKit/helpers
      rm -rf /usr/share/PackageKit/helpers/nix-profile
      ln -sf ${cfg.package}/share/PackageKit/helpers/nix-profile \
             /usr/share/PackageKit/helpers/nix-profile
    '';

    # Install AppStream metadata for GNOME Software / KDE Discover
    # Standard paths: /usr/share/swcatalog/xml/ or /usr/share/app-info/xmls/
    system.activationScripts.packagekit-appstream = mkIf cfg.appstream.enable ''
      # Create both standard AppStream directories
      mkdir -p /usr/share/swcatalog/xml
      mkdir -p /usr/share/swcatalog/icons
      mkdir -p /usr/share/app-info/xmls
      mkdir -p /usr/share/app-info/icons

      ${optionalString (cfg.appstream.package != null) ''
        # Link AppStream data from package (supports both directory layouts)
        for f in ${cfg.appstream.package}/share/swcatalog/xml/*.xml* ${cfg.appstream.package}/share/app-info/xmls/*.xml*; do
          [ -e "$f" ] && ln -sf "$f" /usr/share/swcatalog/xml/ && ln -sf "$f" /usr/share/app-info/xmls/
        done
        for d in ${cfg.appstream.package}/share/swcatalog/icons/* ${cfg.appstream.package}/share/app-info/icons/*; do
          [ -d "$d" ] && ln -sf "$d" /usr/share/swcatalog/icons/ && ln -sf "$d" /usr/share/app-info/icons/
        done
      ''}

      ${optionalString (cfg.appstream.dataPath != null) ''
        # Link AppStream data from path
        for f in ${cfg.appstream.dataPath}/*.xml*; do
          [ -e "$f" ] && ln -sf "$f" /usr/share/swcatalog/xml/ && ln -sf "$f" /usr/share/app-info/xmls/
        done
      ''}
    '';
  };
}
