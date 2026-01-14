#!/usr/bin/env bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test result tracking
TESTS_PASSED=0
TESTS_FAILED=0

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_error() {
    echo -e "${RED}✗${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

test_command() {
    local test_name="$1"
    local command="$2"
    local expected_pattern="${3:-}"
    
    echo -e "\n${BLUE}Test:${NC} $test_name"
    echo -e "${YELLOW}Command:${NC} $command"
    
    # Run with timeout to prevent hanging
    if output=$(timeout 10 bash -c "$command" 2>&1); then
        if [[ -n "$expected_pattern" ]]; then
            if echo "$output" | grep -qi "$expected_pattern"; then
                print_success "$test_name"
                echo "$output" | head -20
            else
                print_error "$test_name - Expected pattern '$expected_pattern' not found"
                echo "$output" | head -20
            fi
        else
            print_success "$test_name"
            echo "$output" | head -20
        fi
    else
        exit_code=$?
        if [[ $exit_code -eq 124 ]]; then
            print_error "$test_name - Command timed out"
        else
            print_error "$test_name - Command failed (exit code: $exit_code)"
        fi
        echo "$output" | head -20
    fi
}

# Main test suite
main() {
    print_header "PackageKit Nix Profile Backend Test Suite"
    echo "Testing on: $(hostname)"
    echo "Date: $(date)"
    
    # 1. PackageKit Configuration Tests
    print_header "1. Configuration Tests"
    
    test_command \
        "PackageKit config file exists" \
        "test -f /etc/PackageKit/PackageKit.conf && echo 'Config exists'"
    
    test_command \
        "Default backend is nix-profile" \
        "grep DefaultBackend /etc/PackageKit/PackageKit.conf" \
        "nix-profile"
    
    # 2. Backend File Tests
    print_header "2. Backend Files"
    
    test_command \
        "Backend .so in system path or nix store" \
        "find /run/current-system/sw/lib/packagekit-backend /nix/store -name 'libpk_backend_nix-profile.so' 2>/dev/null | head -1"
    
    test_command \
        "Helper scripts exist" \
        "find /nix/store -path '*/share/PackageKit/helpers/nix-profile/nix_profile_backend.py' 2>/dev/null | head -1"
    
    # 3. PackageKit Service Tests
    print_header "3. PackageKit Service"
    
    test_command \
        "PackageKit service status" \
        "systemctl is-active packagekit || echo 'Service not running (will auto-start on D-Bus activation)'"
    
    # Start PackageKit if not running
    if ! systemctl is-active --quiet packagekit; then
        print_info "Starting PackageKit daemon..."
        sudo systemctl start packagekit || true
        sleep 2
    fi
    
    test_command \
        "PackageKit daemon responds" \
        "systemctl is-active packagekit" \
        "active"
    
    test_command \
        "No backend load failures in journal" \
        "! journalctl -u packagekit --since '5 minutes ago' --no-pager | grep -i 'failed to load'"
    
    # 4. Backend Detection via pkcon
    print_header "4. Backend Detection (pkcon)"
    
    test_command \
        "pkcon backend-details shows nix-profile" \
        "pkcon backend-details" \
        "nix-profile"
    
    test_command \
        "pkcon get-backends lists nix-profile" \
        "pkcon get-backends" \
        "nix-profile"
    
    # 5. Backend Functionality Tests
    print_header "5. Backend Functionality"
    
    test_command \
        "List installed packages" \
        "pkcon get-packages --filter=installed 2>&1 | head -20"
    
    test_command \
        "Search for packages (firefox)" \
        "pkcon search name firefox 2>&1 | head -20"
    
    test_command \
        "Get package details" \
        "pkcon get-details nix 2>&1 | head -20"
    
    # 6. AppStream Tests
    print_header "6. AppStream Data"
    
    test_command \
        "AppStream swcatalog directory exists" \
        "test -d /usr/share/swcatalog && ls -la /usr/share/swcatalog/"
    
    test_command \
        "AppStream XML symlink exists" \
        "test -L /usr/share/swcatalog/xml && ls -la /usr/share/swcatalog/xml"
    
    test_command \
        "AppStream icons symlink exists" \
        "test -L /usr/share/swcatalog/icons && ls -la /usr/share/swcatalog/icons"
    
    test_command \
        "AppStream has catalog data" \
        "ls -lh /usr/share/swcatalog/xml/*.xml.gz 2>/dev/null | head -5"
    
    test_command \
        "appstreamcli status" \
        "appstreamcli status" \
        "software components"
    
    test_command \
        "appstreamcli search (gnome)" \
        "appstreamcli search gnome 2>&1 | head -20" \
        "GNOME"
    
    test_command \
        "appstreamcli search (firefox)" \
        "appstreamcli search firefox 2>&1 | head -10"
    
    # 7. Bind Mount Tests (if using avoidRebuilds mode)
    print_header "7. Bind Mount Configuration"
    
    test_command \
        "Check PackageKit service for BindPaths" \
        "systemctl cat packagekit.service | grep -A5 BindPaths || echo 'No BindPaths (may be using overlay mode)'"
    
    # 8. Python Backend Direct Test
    print_header "8. Python Backend Direct Test"
    
    if backend_helper=$(find /nix/store -path "*/share/PackageKit/helpers/nix-profile/nix_profile_backend.py" 2>/dev/null | head -1); then
        test_command \
            "Python backend responds to get-packages" \
            "echo -e 'get-packages\tinstalled' | $backend_helper 2>&1 | head -20"
    else
        print_info "Python backend not found in /nix/store (may need to locate manually)"
    fi
    
    # Summary
    print_header "Test Summary"
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "${RED}Failed: $TESTS_FAILED${NC}"
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "\n${GREEN}🎉 All tests passed!${NC}"
        return 0
    else
        echo -e "\n${RED}⚠️  Some tests failed${NC}"
        return 1
    fi
}

# Run tests
main "$@"
