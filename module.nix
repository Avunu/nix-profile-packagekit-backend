{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.packagekit.backends.nix-profile;
in
{
  options.services.packagekit.backends.nix-profile = {
    enable = mkEnableOption "PackageKit Nix profile backend for managing user packages";
    
    package = mkOption {
      type = types.package;
      default = pkgs.packagekit-backend-nix-profile;
      defaultText = literalExpression "pkgs.packagekit-backend-nix-profile";
      description = "The packagekit-nix-profile backend package";
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
  };
}
