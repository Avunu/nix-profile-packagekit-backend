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

  config = mkIf cfg.enable {
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

    # AppStream data for GNOME Software / KDE Discover
    # Adding to systemPackages links share/app-info/ into /run/current-system/sw/share/
    # which is already in XDG_DATA_DIRS, so appstream/gnome-software can find it
    environment.systemPackages = mkIf (cfg.appstream.enable && cfg.appstream.package != null) [
      cfg.appstream.package
    ];
  };
}
