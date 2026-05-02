{
  description = "PackageKit backend for Nix profile management - enables GNOME Software / KDE Discover";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";

    devenv = {
      url = "github:cachix/devenv";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    git-hooks-nix = {
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

    # Offline package search with local Bluge index
    nix-search = {
      url = "github:diamondburned/nix-search";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  nixConfig = {
    extra-trusted-public-keys = "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw=";
    extra-substituters = "https://devenv.cachix.org";
  };

  outputs =
    inputs@{
      self,
      nixpkgs,
      flake-parts,
      bombon,
      nix-search,
      packagekit-src,
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
            nix-search = nix-search.packages.${final.system}.default;
          };
        in
        {
          # The backend .so and helper scripts
          packagekit-backend-nix-profile = backend;

          # nix-search binary for the systemd index-building service
          nix-search = nix-search.packages.${final.system}.default;

          # AppStream data generator - generates metadata by correlating nixpkgs with Flathub
          nixos-appstream-data = final.callPackage ./appstream-package.nix { };
        };

      # Full overlay - modifies packagekit to include our backend
      # Cleaner integration but causes rebuilds of packagekit reverse dependencies
      overlayFull =
        final: prev:
        let
          backend = final.callPackage ./package.nix {
            packagekitSrc = packagekit-src;
            packagekit = prev.packagekit;
            nix-search = nix-search.packages.${final.system}.default;
          };
        in
        {
          packagekit-backend-nix-profile = backend;

          # nix-search binary for the systemd index-building service
          nix-search = nix-search.packages.${final.system}.default;

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

          # AppStream data generator
          nixos-appstream-data = final.callPackage ./appstream-package.nix { };
        };
    in
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.devenv.flakeModule
        inputs.git-hooks-nix.flakeModule
      ];

      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      flake = {
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

      perSystem =
        {
          config,
          system,
          pkgs,
          ...
        }:
        let
          pkgsWithOverlay = import nixpkgs {
            inherit system;
            overlays = [ overlayMinimal ];
          };

          # Python environment with all dependencies for development
          pythonEnv = pkgsWithOverlay.python3.withPackages (ps: [
            ps.pytest
            ps.tldextract
            (ps.toPythonModule pkgsWithOverlay.packagekit)
          ]);
        in
        {
          pre-commit.settings.hooks = {
            ruff.enable = true;
            ruff-format.enable = true;
            nixfmt.enable = true;
            trim-trailing-whitespace.enable = true;
            end-of-file-fixer.enable = true;
            check-json.enable = true;
            check-toml.enable = true;
            check-yaml.enable = true;
          };

          packages = {
            default = pkgsWithOverlay.packagekit-backend-nix-profile;
            backend = pkgsWithOverlay.packagekit-backend-nix-profile;

            # AppStream data - generated by correlating nixpkgs with Flathub
            appstream-data = pkgsWithOverlay.nixos-appstream-data;

            # SBOM generation using bombon (Nix-native CycloneDX SBOM generator)
            sbom = bombon.lib.${system}.buildBom pkgsWithOverlay.packagekit-backend-nix-profile { };
          };

          checks = {
            # Unit tests
            unit-tests =
              pkgsWithOverlay.runCommand "unit-tests"
                {
                  nativeBuildInputs = [ pythonEnv ];
                }
                ''
                  cd ${./.}
                  python -m pytest tests/ -v
                  touch $out
                '';

            # SBOM validation check
            sbom-validation =
              pkgsWithOverlay.runCommand "sbom-validation"
                {
                  nativeBuildInputs = [
                    pkgsWithOverlay.python3
                    pkgsWithOverlay.jq
                  ];
                  sbomFile = "${
                    bombon.lib.${system}.buildBom pkgsWithOverlay.packagekit-backend-nix-profile { }
                  }/bom.json";
                }
                ''
                  echo "Validating SBOM generated by bombon..."

                  # Validate JSON structure
                  if ! ${pkgsWithOverlay.jq}/bin/jq empty "$sbomFile" 2>/dev/null; then
                    echo "Error: SBOM is not valid JSON"
                    exit 1
                  fi

                  # Validate CycloneDX format
                  bomFormat=$(${pkgsWithOverlay.jq}/bin/jq -r '.bomFormat // empty' "$sbomFile")
                  if [ "$bomFormat" != "CycloneDX" ]; then
                    echo "Error: bomFormat must be 'CycloneDX', got '$bomFormat'"
                    exit 1
                  fi

                  # Validate spec version
                  specVersion=$(${pkgsWithOverlay.jq}/bin/jq -r '.specVersion // empty' "$sbomFile")
                  if [ -z "$specVersion" ]; then
                    echo "Error: specVersion is missing"
                    exit 1
                  fi

                  # Count components
                  componentCount=$(${pkgsWithOverlay.jq}/bin/jq '.components | length' "$sbomFile")
                  echo "✓ SBOM validation passed"
                  echo "  Format: CycloneDX $specVersion"
                  echo "  Components: $componentCount"

                  touch $out
                '';

            # Integration test (NixOS VM)
            integration = pkgsWithOverlay.testers.runNixOSTest {
              name = "packagekit-nix-profile-backend";

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
                  services.packagekit.backends.nix-profile.avoidRebuilds = true;
                  services.packagekit.backends.nix-profile.appstream.enable = true;
                  services.packagekit.backends.nix-profile.appstream.package = pkgs.nixos-appstream-data;

                  environment.systemPackages = [
                    pkgs.appstream
                    pkgs.nixos-appstream-data
                  ];

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
                  machine.succeed("systemctl start packagekit")
                  machine.succeed("systemctl is-active packagekit")

                  # Verify the backend loaded successfully
                  result = machine.succeed("journalctl -u packagekit --no-pager")
                  print(f"PackageKit journal: {result}")
                  assert "Failed to load the backend" not in result, "Backend should load successfully"

                  # Try to use pkcon to verify the backend is actually working
                  result = machine.succeed("pkcon backend-details 2>&1 || true")
                  print(f"Backend details: {result}")
                  assert "nix-profile" in result.lower() or "Backend:" in result, "Backend should be available"

                  print("PackageKit started successfully with nix-profile backend!")

                  # Test AppStream data is accessible
                  print("Testing AppStream data...")

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

          devenv.shells.default = {
            packages = [
              pkgsWithOverlay.appstream
              pkgsWithOverlay.glib
              nix-search.packages.${system}.default
              pkgsWithOverlay.packagekit
              pkgsWithOverlay.pkg-config
              pkgsWithOverlay.polkit
              pkgsWithOverlay.pre-commit
              pkgsWithOverlay.pyright
              pkgsWithOverlay.ruff
              pythonEnv
            ];

            enterShell = ''
              # Install git-hooks-nix managed pre-commit hooks
              ${config.pre-commit.installationScript}
            '';

            scripts = {
              pre-commit-run = {
                exec = ''
                  #!/usr/bin/env bash
                  # Run pre-commit hooks
                  pre-commit run --all-files
                '';
                description = "Run pre-commit hooks on all files";
              };

              test = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python -m pytest tests/ --ignore=tests/test_sbom.py -v "$@"
                '';
                description = "Run all tests (unit + e2e)";
              };
              test-unit = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python -m pytest tests/ --ignore=tests/test_sbom.py --ignore=tests/test_e2e_integration.py -v "$@"
                '';
                description = "Run unit tests only";
              };
              test-e2e = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python -m pytest tests/test_e2e_integration.py -v -s "$@"
                '';
                description = "Run E2E integration tests";
              };
              test-e2e-fast = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python -m pytest tests/test_e2e_integration.py -v -m "not slow" "$@"
                '';
                description = "Run E2E tests excluding slow tests";
              };
              test-match = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  if [ -z "$1" ]; then
                    echo "Usage: test-match <pattern>"
                    exit 1
                  fi
                  python -m pytest tests/ --ignore=tests/test_sbom.py -v -k "$1"
                '';
                description = "Run tests matching a pattern";
              };
              refresh = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python appstream.py refresh --output ./nixpkgs-apps.json
                '';
                description = "Refresh nixpkgs-apps.json from local nixpkgs";
              };
              refresh-from = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  if [ -z "$1" ]; then
                    echo "Usage: refresh-from <nixpkgs-path>"
                    exit 1
                  fi
                  python appstream.py refresh --output ./nixpkgs-apps.json --nixpkgs "$1"
                '';
                description = "Refresh nixpkgs-apps.json from a specific nixpkgs path";
              };
              match = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  if [ -z "$1" ]; then
                    echo "Usage: match <flathub-id>"
                    exit 1
                  fi
                  python appstream.py match "$1"
                '';
                description = "Test correlation for a specific Flathub ID";
              };
              info = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  if [ -z "$1" ]; then
                    echo "Usage: info <package>"
                    exit 1
                  fi
                  python appstream.py info "$1"
                '';
                description = "Show info about a nixpkgs package";
              };
              correlate = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python appstream.py correlate --report ./correlation-report.json
                '';
                description = "Run full correlation analysis and generate report";
              };
              generate = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python appstream.py generate --output ./appstream-data
                '';
                description = "Generate AppStream catalog (downloads icons, creates XML)";
              };
              generate-no-icons = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  python appstream.py generate --output ./appstream-data --no-icons
                '';
                description = "Generate AppStream catalog without downloading icons";
              };
              sbom = {
                exec = ''
                  #!/usr/bin/env bash
                  set -e
                  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
                  nix build .#sbom && cp result ./sbom.json && rm result
                '';
                description = "Generate SBOM";
              };
            };
          };

          formatter = pkgsWithOverlay.nixfmt-rfc-style;
        };
    }
    // {
      # Overlays and NixOS modules are defined in the flake section above
    };
}
