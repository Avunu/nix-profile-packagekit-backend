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
    # Overlay that provides the backend package
    overlay = final: prev: {
      packagekit-backend-nix-profile = final.callPackage ./package.nix {
        packagekitSrc = packagekit-src;
      };

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
          ps.brotli
          ps.pytest
          # PackageKit has Python bindings in lib/python*/site-packages/
          # toPythonModule lets withPackages pick them up
          (ps.toPythonModule pkgs.packagekit)
        ]);
      in {
        packages = {
          default = pkgs.packagekit-backend-nix-profile;
          backend = pkgs.packagekit-backend-nix-profile;
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

            nodes.machine = {
              config,
              lib,
              ...
            }: {
              # Import module directly (can't use nixosModules.default in tests due to read-only pkgs)
              imports = [(import ./module.nix)];
              
              # Provide packages directly via module options
              services.packagekit.backends.nix-profile.enable = true;
              services.packagekit.backends.nix-profile.package = pkgs.packagekit-backend-nix-profile;
              services.packagekit.backends.nix-profile.appstream.package = lib.mkForce null;

              # Test user with home directory
              users.users.testuser = {
                isNormalUser = true;
                home = "/home/testuser";
              };

              services.dbus.enable = true;
              environment.systemPackages = [pkgs.packagekit];
            };

            testScript = ''
              machine.start()
              machine.wait_for_unit("multi-user.target")

              # Check backend library is installed
              machine.succeed("test -f /var/lib/PackageKit/plugins/libpk_backend_nix-profile.so")

              # Check helper scripts are installed
              machine.succeed("test -d /usr/share/PackageKit/helpers/nix-profile")
              machine.succeed("test -f /usr/share/PackageKit/helpers/nix-profile/nix_profile_backend.py")

              # Check PackageKit config
              machine.succeed("grep -q 'DefaultBackend=nix-profile' /etc/PackageKit/PackageKit.conf")

              # Wait for D-Bus
              machine.wait_for_unit("dbus.service")

              # Test Python backend directly as testuser
              # Set PackageKit environment variables to suppress library warnings
              output = machine.succeed(
                "su - testuser -c '"
                "export NETWORK=TRUE UID=1000 BACKGROUND=FALSE INTERACTIVE=TRUE; "
                "printf \"get-packages\\tinstalled\\n\" | "
                "/usr/share/PackageKit/helpers/nix-profile/nix_profile_backend.py"
                "' 2>&1 | head -20"
              )
              print(f"Backend output: {output}")

              # Verify we got the expected output format
              assert "finished" in output, "Backend should complete with 'finished'"
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
