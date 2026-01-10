{
  description = "PackageKit backend for Nix profile management - enables GNOME Software / KDE Discover";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # PackageKit source for backend headers and Python library
    packagekit-src = {
      url = "github:PackageKit/PackageKit/v1.3.0";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      packagekit-src,
      ...
    }:
    let
      # Overlay that provides the backend package
      overlay = final: prev: {
        packagekit-backend-nix-profile = final.callPackage ./package.nix {
          packagekitSrc = packagekit-src;
        };
      };
    in
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
      in
      {
        packages = {
          default = pkgs.packagekit-backend-nix-profile;
          backend = pkgs.packagekit-backend-nix-profile;
        };

        # Development shell
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            python3
            python3Packages.brotli
            pyright # Type checker
            pkg-config
            glib
            packagekit
          ];

          shellHook = ''
            echo "PackageKit Nix Profile Backend Development"
            echo ""
            echo "Build:   nix build"
            echo "Test:    ./test_backend.py"
            echo ""
            
            # Add PackageKit Python modules to PYTHONPATH for typechecking
            # Uses the packaged version from nixpkgs which includes enums.py
            export PYTHONPATH="${pkgs.packagekit}/lib/python3.13/site-packages:$PYTHONPATH"
          '';
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    )
    // {
      # NixOS module for easy integration
      nixosModules.default = import ./module.nix;
      nixosModules.nix-profile-backend = import ./module.nix;

      # Overlay for use in other flakes
      overlays.default = overlay;
    };
}
