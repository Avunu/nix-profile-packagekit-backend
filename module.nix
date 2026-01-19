{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
let
  cfg = config.services.packagekit.backends.nix-profile;

  # Get the backend package without modifying packagekit
  backend = pkgs.packagekit-backend-nix-profile;

  # Create a merged backends directory with both original and our backend
  mergedBackends = pkgs.runCommand "packagekit-backends-merged" { } ''
    mkdir -p $out/lib/packagekit-backend
    # Link all backends from the original packagekit
    for f in ${pkgs.packagekit}/lib/packagekit-backend/*.so; do
      ln -s "$f" $out/lib/packagekit-backend/
    done
    # Link our backend (this will add it, not replace)
    for f in ${backend}/lib/packagekit-backend/*.so; do
      ln -s "$f" $out/lib/packagekit-backend/
    done
    # Also need helper scripts
    mkdir -p $out/share/PackageKit/helpers
    if [ -d ${pkgs.packagekit}/share/PackageKit/helpers ]; then
      for d in ${pkgs.packagekit}/share/PackageKit/helpers/*; do
        ln -s "$d" $out/share/PackageKit/helpers/ 2>/dev/null || true
      done
    fi
    ln -sfn ${backend}/share/PackageKit/helpers/nix-profile $out/share/PackageKit/helpers/nix-profile
  '';
in
{
  options.services.packagekit.backends.nix-profile = {
    enable = mkEnableOption "PackageKit Nix profile backend for managing user packages";

    # Option to choose between rebuild approach (cleaner) vs runtime overlay (avoids rebuilds)
    avoidRebuilds = mkOption {
      type = types.bool;
      default = true;
      description = ''
        If true, use runtime bind mounts to inject the backend without rebuilding
        packages that depend on PackageKit (like Dolphin, KWin, Plasma).

        If false, use the overlay approach which rebuilds PackageKit and its
        reverse dependencies but is cleaner.
      '';
    };

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
    }

    # Runtime bind mount approach - avoids rebuilding KDE/GNOME packages
    (mkIf cfg.avoidRebuilds {
      # Use systemd bind mounts to inject our backend into PackageKit's view
      # This avoids modifying packagekit itself, preventing rebuild cascades
      systemd.services.packagekit.serviceConfig = {
        # Bind mount our merged backends directory over packagekit's backend dir
        BindPaths = [
          "${mergedBackends}/lib/packagekit-backend:${pkgs.packagekit}/lib/packagekit-backend"
          "${mergedBackends}/share/PackageKit/helpers:${pkgs.packagekit}/share/PackageKit/helpers"
        ];
      };
    })

    # Overlay approach - cleaner but causes rebuilds
    # (enabled when avoidRebuilds = false)
    # The flake's overlay replaces pkgs.packagekit with our version that
    # includes the nix-profile backend

    # AppStream data for GNOME Software / KDE Discover
    (mkIf (cfg.appstream.enable && cfg.appstream.package != null) {
      environment.systemPackages = [ cfg.appstream.package ];

      environment.pathsToLink = [
        "/share/swcatalog"
        "/share/app-info" # Legacy compatibility
      ];

      # Create symlinks in /usr/share for AppStream to find the catalog
      # AppStream looks in /usr/share/swcatalog by default on most distros
      systemd.tmpfiles.rules =
        let
          appstreamPkg = cfg.appstream.package;
        in
        [
          "d /usr/share 0755 root root -"
          "d /usr/share/swcatalog 0755 root root -"
          "L+ /usr/share/swcatalog/xml - - - - ${appstreamPkg}/share/swcatalog/xml"
          "L+ /usr/share/swcatalog/icons - - - - ${appstreamPkg}/share/swcatalog/icons"
        ];
    })

    # Ensure ~/.nix-profile/share is in XDG_DATA_DIRS for desktop file discovery
    # This allows GNOME/KDE to find .desktop files installed via nix profile
    {
      environment.sessionVariables.XDG_DATA_DIRS = [
        "$HOME/.nix-profile/share"
      ];

      # Register MIME handlers from nix-profile apps (x-scheme-handler/* types)
      # This is needed because nix-profile directories are read-only and can't have
      # mimeinfo.cache generated, unlike system packages in environment.systemPackages
      systemd.user.services.nix-profile-mime-handler = {
        description = "Register MIME handlers from nix-profile applications";
        wantedBy = [ "default.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        path = with pkgs; [
          coreutils
          gnugrep
          gnused
        ];
        script = ''
          PROFILE_APPS="$HOME/.nix-profile/share/applications"
          MIMEAPPS="$HOME/.config/mimeapps.list"

          [ -d "$PROFILE_APPS" ] || exit 0

          mkdir -p "$(dirname "$MIMEAPPS")"
          touch "$MIMEAPPS"

          # Ensure [Default Applications] section exists
          grep -q '^\[Default Applications\]' "$MIMEAPPS" || \
            echo -e "\n[Default Applications]" >> "$MIMEAPPS"

          # Scan desktop files for x-scheme-handler entries
          for desktop in "$PROFILE_APPS"/*.desktop; do
            [ -f "$desktop" ] || continue
            basename=$(basename "$desktop")

            # Extract MimeType line and process x-scheme-handler entries
            grep -h '^MimeType=' "$desktop" 2>/dev/null | \
              sed 's/^MimeType=//' | tr ';' '\n' | \
              grep '^x-scheme-handler/' | while read -r mime; do
                [ -z "$mime" ] && continue
                # Only add if not already set (preserves user customizations)
                if ! grep -q "^$mime=" "$MIMEAPPS" 2>/dev/null; then
                  sed -i "/^\[Default Applications\]/a $mime=$basename" "$MIMEAPPS"
                fi
              done
          done
        '';
      };
    }
  ]);
}
