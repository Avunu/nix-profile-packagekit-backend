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

        # Python environment with all dependencies for development
        # This creates a wrapped Python with packages in sys.path
        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.brotli
          # PackageKit has Python bindings in lib/python*/site-packages/
          # toPythonModule lets withPackages pick them up
          (ps.toPythonModule pkgs.packagekit)
        ]);
      in
      {
        packages = {
          default = pkgs.packagekit-backend-nix-profile;
          backend = pkgs.packagekit-backend-nix-profile;
        };

        # Development shell
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.pyright
            pkgs.pkg-config
            pkgs.glib
            pkgs.packagekit
            pkgs.nix-search-cli
          ];

          shellHook = ''
            echo "PackageKit Nix Profile Backend Development"
            echo ""
            echo "Build:   nix build"
            echo "Test:    ./test_backend.py"
            echo ""
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
