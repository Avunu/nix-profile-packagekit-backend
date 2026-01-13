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
      default = pkgs.packagekit-nix;
      defaultText = literalExpression "pkgs.packagekit-nix";
      description = "The wrapped PackageKit package with nix-profile backend included";
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

    # Configure PackageKit to use nix-profile backend
    services.packagekit.settings = {
      Daemon = {
        DefaultBackend = "nix-profile";
      };
    };

    # Override the PackageKit packages to use our wrapped version with the backend included
    # This replaces the default pkgs.packagekit with pkgs.packagekit-nix
    services.dbus.packages = mkForce [cfg.package];
    environment.systemPackages = mkForce [cfg.package];
    systemd.packages = mkForce [cfg.package];

    # Install AppStream metadata for GNOME Software / KDE Discover
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
