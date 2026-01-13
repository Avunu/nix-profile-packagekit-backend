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

    appstream = {
      enable = mkEnableOption "AppStream metadata for nixpkgs (enables app listings in GNOME Software/KDE Discover)";

      package = mkOption {
        type = types.nullOr types.package;
        default = pkgs.nixos-appstream-data or null;
        defaultText = literalExpression "pkgs.nixos-appstream-data";
        description = ''
          AppStream data package for nixpkgs.
          Should provide share/app-info/xmls/ and share/app-info/icons/.
        '';
      };
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      # Enable PackageKit with our backend
      services.packagekit.enable = true;

      # Configure PackageKit to use nix-profile backend
      services.packagekit.settings = {
        Daemon = {
          DefaultBackend = "nix-profile";
        };
      };

      # The flake's overlay replaces pkgs.packagekit with our version that
      # includes the nix-profile backend, so services.packagekit automatically
      # gets our wrapped version.
    }

    # AppStream data for GNOME Software / KDE Discover
    # Adding to systemPackages links share/app-info/ into /run/current-system/sw/share/
    # which is already in XDG_DATA_DIRS, so appstream/gnome-software can find it
    (mkIf (cfg.appstream.enable && cfg.appstream.package != null) {
      environment.systemPackages = [ cfg.appstream.package ];

      # Link app-info paths for AppStream 1.0+ compatibility
      # AppStream 1.0+ looks in /usr/share/swcatalog and /var/lib/swcatalog
      # The old format uses app-info/xmls, new format uses swcatalog/xml
      # We also need app-info for backward compat with older tools
      environment.pathsToLink = [
        "/share/app-info"
        "/share/swcatalog"
      ];

      # Create /usr/share/swcatalog symlinks for AppStream 1.0+ catalog discovery
      # AppStream looks in hardcoded /usr/share/swcatalog, not XDG_DATA_DIRS
      # Use tmpfiles to create symlinks to the appstream data package in the nix store
      systemd.tmpfiles.rules = let
        appstreamPkg = cfg.appstream.package;
      in [
        # Create parent directories
        "d /usr/share 0755 root root -"
        "d /usr/share/swcatalog 0755 root root -"

        # Create symlink: /usr/share/swcatalog/xml -> <appstream-package>/share/app-info/xmls
        # AppStream 1.0+ expects 'xml' (singular), data package has 'xmls' (plural)
        "L+ /usr/share/swcatalog/xml - - - - ${appstreamPkg}/share/app-info/xmls"

        # Create symlink: /usr/share/swcatalog/icons -> <appstream-package>/share/app-info/icons
        "L+ /usr/share/swcatalog/icons - - - - ${appstreamPkg}/share/app-info/icons"

        # Also link for older tools that look in app-info
        "L+ /usr/share/app-info - - - - ${appstreamPkg}/share/app-info"
      ];
    })
  ]);
}
