#!/usr/bin/env bash
# SBOM (Software Bill of Materials) management script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SBOM_FILE="${SCRIPT_DIR}/sbom.json"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
SBOM Management Script

Usage: $0 <command>

Commands:
    generate    Generate SBOM file (sbom.json)
    validate    Validate existing SBOM file
    update      Generate and validate SBOM (same as generate + validate)
    check       Validate SBOM without regenerating
    help        Show this help message

Examples:
    $0 generate    # Generate new SBOM
    $0 validate    # Validate current SBOM
    $0 update      # Update and validate SBOM

The SBOM is stored in: ${SBOM_FILE}
Format: CycloneDX 1.5 (JSON)
EOF
}

generate_sbom() {
    echo -e "${YELLOW}Generating SBOM...${NC}"
    python3 "${SCRIPT_DIR}/generate_sbom.py"
    echo -e "${GREEN}✓ SBOM generated successfully${NC}"
}

validate_sbom() {
    if [[ ! -f "$SBOM_FILE" ]]; then
        echo -e "${RED}✗ Error: SBOM file not found: ${SBOM_FILE}${NC}"
        echo "Run '$0 generate' to create it first."
        return 1
    fi

    echo -e "${YELLOW}Validating SBOM...${NC}"
    if python3 "${SCRIPT_DIR}/validate_sbom.py"; then
        echo -e "${GREEN}✓ SBOM validation passed${NC}"
        return 0
    else
        echo -e "${RED}✗ SBOM validation failed${NC}"
        return 1
    fi
}

update_sbom() {
    generate_sbom
    echo ""
    validate_sbom
}

main() {
    local command="${1:-}"

    case "$command" in
        generate)
            generate_sbom
            ;;
        validate|check)
            validate_sbom
            ;;
        update)
            update_sbom
            ;;
        help|--help|-h)
            usage
            ;;
        "")
            echo -e "${RED}Error: No command specified${NC}\n"
            usage
            exit 1
            ;;
        *)
            echo -e "${RED}Error: Unknown command: $command${NC}\n"
            usage
            exit 1
            ;;
    esac
}

main "$@"
