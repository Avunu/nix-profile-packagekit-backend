# AppStream generation commands
# Run with: just <command>

# Default: show available commands
default:
    @just --list

# Refresh nixpkgs-apps.json from local nixpkgs store
refresh:
    python appstream.py refresh --output ./nixpkgs-apps.json

# Refresh from a specific nixpkgs path
refresh-from path:
    python appstream.py refresh --output ./nixpkgs-apps.json --nixpkgs {{path}}

# Test correlation for a specific Flathub ID
match id:
    python appstream.py match {{id}}

# Look up info about a nixpkgs package
info package:
    python appstream.py info {{package}}

# Run full correlation analysis and generate report
correlate:
    python appstream.py correlate --report ./correlation-report.json

# Generate AppStream catalog (downloads icons, creates XML)
generate:
    python appstream.py generate --output ./appstream-data

# Generate without downloading icons
generate-no-icons:
    python appstream.py generate --output ./appstream-data --no-icons
