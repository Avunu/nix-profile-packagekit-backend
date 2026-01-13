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

    # AppStream data for nixpkgs (optional, for GUI software centers)
    # Note: This data may be outdated - consider regenerating with nixos-appstream-generator
    appstream-data = {
      url = "github:snowfallorg/nixos-appstream-data";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    packagekit-src,
    appstream-data,
    ...
  }: let
    # Overlay that provides the backend package and replaces PackageKit
    overlay = final: prev: let
      # Build backend against the original packagekit to avoid infinite recursion
      backend = final.callPackage ./package.nix {
        packagekitSrc = packagekit-src;
        packagekit = prev.packagekit;
      };
    in {
      # The backend .so and helper scripts
      packagekit-backend-nix-profile = backend;

      # Override packagekit to include our backend in its lib directory
      # We need to rebuild with our backend copied into the output
      packagekit = prev.packagekit.overrideAttrs (oldAttrs: {
        postInstall = (oldAttrs.postInstall or "") + ''
          # Add nix-profile backend
          ln -sf ${backend}/lib/packagekit-backend/*.so $out/lib/packagekit-backend/

          # Link helper scripts (create parent dir if needed)
          mkdir -p $out/share/PackageKit/helpers
          ln -sfn ${backend}/share/PackageKit/helpers/nix-profile $out/share/PackageKit/helpers/nix-profile
        '';
      });

      # Keep packagekit-nix as an alias for compatibility
      packagekit-nix = final.packagekit;

      # Re-export upstream AppStream data package
      nixos-appstream-data = appstream-data.packages.${final.system}.default;
    };
  in
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [overlay];
        };

        # Python environment with all dependencies for development
        # This creates a wrapped Python with packages in sys.path
        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.pytest
          # PackageKit has Python bindings in lib/python*/site-packages/
          # toPythonModule lets withPackages pick them up
          (ps.toPythonModule pkgs.packagekit)
        ]);
      in {
        packages = {
          default = pkgs.packagekit-backend-nix-profile;
          backend = pkgs.packagekit-backend-nix-profile;
          packagekit-nix = pkgs.packagekit-nix;
          appstream-data = pkgs.nixos-appstream-data;
        };

        # Checks (run with: nix flake check)
        checks = {
          # Unit tests
          unit-tests =
            pkgs.runCommand "unit-tests"
            {
              nativeBuildInputs = [pythonEnv];
            }
            ''
              cd ${./.}
              python -m pytest tests/ -v
              touch $out
            '';

          # Integration test (NixOS VM)
          # Run with: nix build .#checks.x86_64-linux.integration
          integration = pkgs.testers.runNixOSTest {
            name = "packagekit-nix-profile-backend";

            # Use defaults to add our overlay to all nodes
            defaults = {lib, ...}: {
              nixpkgs.overlays = lib.mkForce [overlay];
            };

            nodes.machine = {
              config,
              lib,
              ...
            }: {
              imports = [(import ./module.nix)];

              services.packagekit.backends.nix-profile.enable = true;
              services.packagekit.backends.nix-profile.appstream.enable = false;

              users.users.testuser = {
                isNormalUser = true;
                home = "/home/testuser";
              };

              services.dbus.enable = true;
            };

            testScript = ''
              machine.start()
              machine.wait_for_unit("multi-user.target")

              # Check backend library is installed in packagekit's directory
              machine.succeed("test -f /run/current-system/sw/lib/packagekit-backend/libpk_backend_nix-profile.so")

              # Check PackageKit config
              machine.succeed("grep -q 'DefaultBackend=nix-profile' /etc/PackageKit/PackageKit.conf")

              # Wait for D-Bus
              machine.wait_for_unit("dbus.service")

              # Test PackageKit daemon can start and stays running
              machine.succeed("systemctl start packagekit")
              machine.succeed("systemctl is-active packagekit")

              # Verify the backend loaded successfully (no error in journal)
              result = machine.succeed("journalctl -u packagekit --no-pager")
              assert "Failed to load the backend" not in result, "Backend should load successfully"
              print("PackageKit started successfully with nix-profile backend!")
            '';
          };
        };

        # Development shell
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.pyright
            pkgs.ruff
            pkgs.pre-commit
            pkgs.pkg-config
            pkgs.glib
            pkgs.packagekit
            pkgs.nix-search-cli
          ];

          shellHook = ''
            echo "PackageKit Nix Profile Backend Development"
            echo ""
            echo "Build:    nix build"
            echo "Test:     pytest tests/"
            echo "Lint:     ruff check . --fix"
            echo "Format:   ruff format ."
            echo "Check:    nix flake check"
            echo "VM Test:  nix build .#checks.x86_64-linux.integration"
            echo ""
          '';
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    )
    // {
      # NixOS module for easy integration (includes overlay automatically)
      nixosModules.default = {
        config,
        lib,
        pkgs,
        ...
      }: {
        imports = [(import ./module.nix)];
        # Always apply overlay so pkgs.packagekit-backend-nix-profile is available
        nixpkgs.overlays = [overlay];
      };
      nixosModules.nix-profile-backend = self.nixosModules.default;

      # Overlay for use in other flakes (if needed separately)
      overlays.default = overlay;
    };
}
