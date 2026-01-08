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
    
    # The key: we need to get PackageKit to use our backend
    # This requires:
    # 1. Backend .so in lib/packagekit-backend/
    # 2. Python helpers in share/PackageKit/helpers/<backend>/
    # 3. PackageKit.conf DefaultBackend setting
    
    # Method: Overlay the backend directory into PackageKit's search path
    # PackageKit searches: /usr/lib/packagekit-backend, /var/lib/PackageKit/plugins
    
    # Create activation script to link backend
    system.activationScripts.packagekit-nix-profile = ''
      # Link backend shared library
      mkdir -p /var/lib/PackageKit/plugins
      ln -sf ${cfg.package}/lib/packagekit-backend/libpk_backend_nix-profile.so \
             /var/lib/PackageKit/plugins/
      
      # Link helper scripts - PackageKit spawn looks in share/PackageKit/helpers/
      mkdir -p /usr/share/PackageKit/helpers
      rm -rf /usr/share/PackageKit/helpers/nix-profile
      ln -sf ${cfg.package}/share/PackageKit/helpers/nix-profile \
             /usr/share/PackageKit/helpers/nix-profile
    '';
    
    # Configure PackageKit to use nix-profile backend
    environment.etc."PackageKit/PackageKit.conf".text = ''
      [Daemon]
      DefaultBackend=nix-profile
      KeepCache=false
      
      [Logging]
      MaximumLevel=debug
    '';
  };
}
