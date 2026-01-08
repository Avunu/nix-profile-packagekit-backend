# Changelog - Nix Profile PackageKit Backend

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Multi-architecture support (aarch64, etc.)
- Better version comparison logic
- Comprehensive test suite
- Performance optimizations
- Flake integration

## [1.0.0-alpha] - 2025-01-01

### Added - Initial Implementation

#### Core Backend
- Complete PackageKit Python backend implementation
- Support for all standard query operations
- Package installation, removal, and updates
- Nix internal-json log parsing for progress tracking
- Intelligent progress reporting based on nix activities

#### Profile Management
- Parsing of ~/.nix-profile/manifest.json
- Extraction of package names and versions from store paths
- Package index lookup for remove/upgrade operations
- Detection of empty or non-existent profiles

#### Appdata Integration
- Download appdata streams from GitHub releases
- SQLite database building from YAML appdata
- Full-text search using FTS5
- Category-based package queries
- In-memory metadata caching
- Automatic cache refresh with age checking

#### PackageKit Methods
- `resolve()` - Resolve package names
- `search_names()` - Search by name
- `search_details()` - Search descriptions
- `search_groups()` - Search by category
- `get_details()` - Get package metadata
- `get_packages()` - List packages
- `get_updates()` - Check for updates
- `get_update_detail()` - Update details
- `install_packages()` - Install to profile
- `remove_packages()` - Remove from profile
- `update_packages()` - Update specific packages
- `update_system()` - Update all packages
- `refresh_cache()` - Update appdata

#### Documentation
- Comprehensive README with architecture details
- Quick start guide for new users
- TODO roadmap for future development
- Project summary with metrics
- Configuration file with examples
- Test script for verification

#### Build System
- Meson build integration
- Installation scripts
- Python requirements specification

### Known Limitations
- Version detection is heuristic-based
- No dependency information available
- No file list support
- Single architecture (x86_64-linux)
- Limited error messages in some cases

### Technical Details
- **Language**: Python 3.6+
- **Lines of Code**: ~1,400 (excluding documentation)
- **Documentation**: ~2,000 lines
- **Dependencies**: PyYAML, sqlite3 (built-in)
- **Nix Version**: Requires Nix 2.4+ with profile support

### File Structure
```
nix-profile/
├── nixProfileBackend.py    (770 lines) - Main backend
├── nix_profile.py          (240 lines) - Profile parser
├── nixpkgs_appdata.py      (400 lines) - Appdata manager
├── meson.build                          - Build config
├── nix-profile.conf                     - Backend config
├── requirements.txt                     - Python deps
├── test_backend.py                      - Test script
├── README.md                            - Full docs
├── QUICKSTART.md                        - Quick start
├── TODO.md                              - Roadmap
├── SUMMARY.md                           - Project summary
└── CHANGELOG.md                         - This file
```

## Versioning Strategy

- **Major version** (1.x.x): Breaking changes to API or behavior
- **Minor version** (x.1.x): New features, non-breaking changes
- **Patch version** (x.x.1): Bug fixes, documentation updates

## Future Milestones

### v1.0.0-beta (Target: Q1 2025)
- Comprehensive testing with GNOME Software
- Testing with KDE Discover
- Bug fixes from alpha testing
- Performance improvements

### v1.0.0 (Target: Q2 2025)
- Production-ready release
- Full documentation
- Stable API
- Community feedback incorporated

### v1.1.0 (Target: Q3 2025)
- Multi-architecture support
- Better version comparison
- Flake integration
- Generation management

### v2.0.0 (Target: 2026)
- Standalone project
- Independent releases
- Extended feature set
- Community-driven development

## Notes

- This is the initial implementation as part of PackageKit
- Will eventually become a standalone project
- Contributions welcome!
- See TODO.md for detailed roadmap

---

**Legend**:
- Added: New features
- Changed: Changes in existing functionality
- Deprecated: Soon-to-be removed features
- Removed: Removed features
- Fixed: Bug fixes
- Security: Security fixes
