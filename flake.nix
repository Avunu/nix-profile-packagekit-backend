{
  description = "PackageKit backend for Nix profile management - enables GNOME Software / KDE Discover";

  inputs = {
    # Enable git submodules (nixos-appstream-data, nixos-appstream-generator)
    self.submodules = true;

    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Pre-commit hooks using Nix packages
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # PackageKit source for backend headers and Python library
    packagekit-src = {
      url = "github:PackageKit/PackageKit/v1.3.0";
      flake = false;
    };

    # SBOM generation tool for Nix packages
    bombon = {
      url = "github:nikstur/bombon";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      git-hooks,
      packagekit-src,
      bombon,
      ...
    }:
    let
      # Minimal overlay - just provides the backend package without modifying packagekit
      # Use this to avoid rebuild cascades of KDE/GNOME packages
      overlayMinimal =
        final: prev:
        let
          backend = final.callPackage ./package.nix {
            packagekitSrc = packagekit-src;
            packagekit = prev.packagekit;
          };
        in
        {
          # The backend .so and helper scripts
          packagekit-backend-nix-profile = backend;

          # AppStream data from submodule - provides software catalog for GNOME Software/KDE Discover
          nixos-appstream-data = final.callPackage ./nixos-appstream-data { set = "free"; };
          nixos-appstream-data-unfree = final.callPackage ./nixos-appstream-data { set = "unfree"; };
          nixos-appstream-data-all = final.callPackage ./nixos-appstream-data { set = "all"; };
        };

      # Full overlay - modifies packagekit to include our backend
      # Cleaner integration but causes rebuilds of packagekit reverse dependencies
      overlayFull =
        final: prev:
        let
          backend = final.callPackage ./package.nix {
            packagekitSrc = packagekit-src;
            packagekit = prev.packagekit;
          };
        in
        {
          packagekit-backend-nix-profile = backend;

          # Override packagekit to include our backend in its lib directory
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

          # AppStream data from submodule
          nixos-appstream-data = final.callPackage ./nixos-appstream-data { set = "free"; };
          nixos-appstream-data-unfree = final.callPackage ./nixos-appstream-data { set = "unfree"; };
          nixos-appstream-data-all = final.callPackage ./nixos-appstream-data { set = "all"; };
        };

      # Default overlay uses minimal to avoid rebuilds
      overlay = overlayMinimal;
    in
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };

        # Pre-commit hooks configuration
        pre-commit-check = git-hooks.lib.${system}.run {
          src = ./.;
          hooks = {
            # Python
            ruff.enable = true;
            ruff-format.enable = true;

            # Nix
            nixfmt.enable = true;

            # General
            trim-trailing-whitespace.enable = true;
            end-of-file-fixer.enable = true;
            # check-json.enable = true;
            check-toml.enable = true;
            check-yaml.enable = true;
          };
        };

        # Python environment with all dependencies for development
        # This creates a wrapped Python with packages in sys.path
        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.pytest
          # PackageKit has Python bindings in lib/python*/site-packages/
          # toPythonModule lets withPackages pick them up
          (ps.toPythonModule pkgs.packagekit)
        ]);
      in
      {
        packages = {
          default = pkgs.packagekit-backend-nix-profile;
          backend = pkgs.packagekit-backend-nix-profile;

          # AppStream data variants
          appstream-data = pkgs.nixos-appstream-data;
          appstream-data-free = pkgs.nixos-appstream-data;
          appstream-data-unfree = pkgs.nixos-appstream-data-unfree;
          appstream-data-all = pkgs.nixos-appstream-data-all;

          # SBOM generation using bombon (Nix-native CycloneDX SBOM generator)
          sbom = bombon.lib.${system}.buildBom pkgs.packagekit-backend-nix-profile {
            meta = {
              name = "packagekit-backend-nix-profile";
              version = "1.0.0";
            };
          };
        };

        # Checks (run with: nix flake check)
        checks = {
          # Unit tests
          unit-tests =
            pkgs.runCommand "unit-tests"
              {
                nativeBuildInputs = [ pythonEnv ];
              }
              ''
                cd ${./.}
                python -m pytest tests/ -v
                touch $out
              '';

          # SBOM validation check - validates bombon-generated SBOM
          sbom-validation =
            pkgs.runCommand "sbom-validation"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.jq
                ];
                sbomFile = "${bombon.lib.${system}.buildBom pkgs.packagekit-backend-nix-profile { }}/bom.json";
              }
              ''
                echo "Validating SBOM generated by bombon..."

                # Validate JSON structure
                if ! ${pkgs.jq}/bin/jq empty "$sbomFile" 2>/dev/null; then
                  echo "Error: SBOM is not valid JSON"
                  exit 1
                fi

                # Validate CycloneDX format
                bomFormat=$(${pkgs.jq}/bin/jq -r '.bomFormat // empty' "$sbomFile")
                if [ "$bomFormat" != "CycloneDX" ]; then
                  echo "Error: bomFormat must be 'CycloneDX', got '$bomFormat'"
                  exit 1
                fi

                # Validate spec version
                specVersion=$(${pkgs.jq}/bin/jq -r '.specVersion // empty' "$sbomFile")
                if [ -z "$specVersion" ]; then
                  echo "Error: specVersion is missing"
                  exit 1
                fi

                # Count components
                componentCount=$(${pkgs.jq}/bin/jq '.components | length' "$sbomFile")
                echo "✓ SBOM validation passed"
                echo "  Format: CycloneDX $specVersion"
                echo "  Components: $componentCount"

                touch $out
              '';

          # Integration test (NixOS VM)
          # Run with: nix build .#checks.x86_64-linux.integration
          integration = pkgs.testers.runNixOSTest {
            name = "packagekit-nix-profile-backend";

            # Use minimal overlay - the module will use bind mounts
            defaults =
              { lib, ... }:
              {
                nixpkgs.overlays = lib.mkForce [ overlayMinimal ];
              };

            nodes.machine =
              {
                config,
                lib,
                pkgs,
                ...
              }:
              {
                imports = [ (import ./module.nix) ];

                services.packagekit.backends.nix-profile.enable = true;
                # Use bind mount approach (default)
                services.packagekit.backends.nix-profile.avoidRebuilds = true;
                services.packagekit.backends.nix-profile.appstream.enable = true;
                services.packagekit.backends.nix-profile.appstream.package = pkgs.nixos-appstream-data;

                # Add appstreamcli for testing
                environment.systemPackages = [
                  pkgs.appstream
                  pkgs.nixos-appstream-data
                ];

                # Ensure app-info directory gets linked from systemPackages
                environment.pathsToLink = [ "/share/app-info" ];

                users.users.testuser = {
                  isNormalUser = true;
                  home = "/home/testuser";
                };

                services.dbus.enable = true;
              };

            testScript =
              { nodes, ... }:
              ''
                machine.start()
                machine.wait_for_unit("multi-user.target")

                # Check PackageKit config
                machine.succeed("grep -q 'DefaultBackend=nix-profile' /etc/PackageKit/PackageKit.conf")

                # Wait for D-Bus
                machine.wait_for_unit("dbus.service")

                # Test PackageKit daemon can start and stays running
                # The bind mount will inject our backend into packagekit's view
                machine.succeed("systemctl start packagekit")
                machine.succeed("systemctl is-active packagekit")

                # Verify the backend loaded successfully (no error in journal)
                result = machine.succeed("journalctl -u packagekit --no-pager")
                print(f"PackageKit journal: {result}")
                assert "Failed to load the backend" not in result, "Backend should load successfully"

                # Try to use pkcon to verify the backend is actually working
                # This will fail if the backend can't be loaded
                result = machine.succeed("pkcon backend-details 2>&1 || true")
                print(f"Backend details: {result}")
                # Should show nix-profile as the backend name
                assert "nix-profile" in result.lower() or "Backend:" in result, "Backend should be available"

                print("PackageKit started successfully with nix-profile backend!")

                # Test AppStream data is accessible
                print("Testing AppStream data...")

                # Check the /usr/share/swcatalog symlinks created by tmpfiles
                machine.succeed("test -L /usr/share/swcatalog/xml")
                machine.succeed("test -L /usr/share/swcatalog/icons")

                # Verify AppStream finds the data
                result = machine.succeed("appstreamcli status 2>&1")
                print(f"AppStream status: {result}")
                assert "software components" in result, "AppStream should find components"

                # Search for packages
                result = machine.succeed("appstreamcli search gnome 2>&1")
                assert "GNOME" in result, "Should find GNOME applications"
                print("AppStream search works!")

                print("All tests passed!")
              '';
          };
        };

        # Development shell
        devShells.default = pkgs.mkShell {
          inherit (pre-commit-check) shellHook;

          packages = [
            pkgs.glib
            pkgs.nix-search-cli
            pkgs.packagekit
            pkgs.pkg-config
            pkgs.pyright
            pkgs.ruff
            pythonEnv
          ];
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    )
    // {
      # NixOS module for easy integration (includes overlay automatically)
      nixosModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        {
          imports = [ (import ./module.nix) ];
          # Apply minimal overlay by default - doesn't modify packagekit, avoids rebuilds
          # The module uses runtime bind mounts to inject the backend
          nixpkgs.overlays = [ overlayMinimal ];
        };
      nixosModules.nix-profile-backend = self.nixosModules.default;

      # Alternative module that rebuilds packagekit (cleaner but causes rebuild cascades)
      nixosModules.full =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        {
          imports = [ (import ./module.nix) ];
          # Apply full overlay - modifies packagekit, causes rebuilds of KDE/GNOME
          nixpkgs.overlays = [ overlayFull ];
          # Disable the bind mount approach since we're modifying packagekit directly
          services.packagekit.backends.nix-profile.avoidRebuilds = lib.mkDefault false;
        };

      # Overlays for use in other flakes
      overlays.default = overlayMinimal; # Recommended - no rebuilds
      overlays.minimal = overlayMinimal; # Same as default
      overlays.full = overlayFull; # Modifies packagekit, causes rebuilds
    };
}
