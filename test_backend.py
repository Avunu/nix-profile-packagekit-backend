#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nix Profile Backend for PackageKit

Simple test script to verify the backend works.
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from nixProfileBackend import PackageKitNixProfileBackend

def test_backend():
    """Run a simple test of the backend."""
    print("Testing Nix Profile PackageKit Backend")
    print("=" * 50)
    
    # Create backend instance
    backend = PackageKitNixProfileBackend('')
    
    # Test profile reading
    print("\n1. Testing profile parsing...")
    try:
        installed = backend.profile.get_installed_packages()
        print(f"   Found {len(installed)} installed packages")
        if installed:
            print("   Examples:")
            for i, (name, version) in enumerate(list(installed.items())[:5]):
                print(f"     - {name}: {version}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test appdata cache
    print("\n2. Testing appdata cache...")
    try:
        # Check if cache exists
        if backend.appdata.db_file.exists():
            print(f"   Cache found at: {backend.appdata.db_file}")
        else:
            print("   Cache not found. Run 'pkcon refresh' to download.")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test package search
    print("\n3. Testing package search (if cache exists)...")
    try:
        results = backend.appdata.search_packages(['firefox'], search_descriptions=False)
        if results:
            print(f"   Found {len(results)} results for 'firefox'")
            for pkg, meta in list(results.items())[:3]:
                print(f"     - {pkg}: {meta.get('summary', 'No summary')[:60]}")
        else:
            print("   No results (cache may not be available)")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n" + "=" * 50)
    print("Test complete!")
    print("\nTo use this backend:")
    print("  1. Install with meson/ninja")
    print("  2. Run: pkcon refresh")
    print("  3. Run: pkcon search name firefox")
    print("  4. Run: pkcon install firefox")

if __name__ == '__main__':
    test_backend()
