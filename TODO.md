# TODO & Roadmap - Nix Profile PackageKit Backend

## Phase 1: Core Functionality ✅ COMPLETE

- [x] Basic backend structure
- [x] Nix profile parsing (manifest.json)
- [x] Appdata integration (dual source: nix-data-db + nixos-appstream-data)
- [x] Package search (name, description, category)
- [x] Install/remove/update operations
- [x] Progress tracking via internal-json logs
- [x] SQLite caching for metadata
- [x] AppStream XML parsing for categories/icons/screenshots
- [x] Documentation and quick start
- [x] Standalone project structure
- [x] Flake-based deployment
- [x] NixOS module with configuration options
- [x] uv dependency management with lock file

## Phase 2: Deployment & Packaging ✅ COMPLETE

- [x] **Flake configuration**
  - flake.nix with uv2nix integration
  - package.nix derivation
  - Development shell

- [x] **NixOS module**
  - services.packagekit.backends.nix-profile options
  - Automatic backend installation
  - Configuration file generation
  - Cache directory management

- [x] **Dependency management**
  - pyproject.toml with metadata
  - uv.lock for reproducible builds
  - Proper Python packaging

- [x] **Documentation**
  - DEPLOYMENT.md for installation
  - TESTING.md for validation
  - Updated README for standalone usage

## Phase 3: Testing & Validation (IN PROGRESS)

### High Priority

- [ ] **Version comparison logic**
  - Implement proper Nix version comparison
  - Handle complex version strings
  - Detect actual updates vs. rebuilds

- [ ] **Error handling improvements**
  - Better error messages for common failures
  - Graceful degradation when appdata unavailable
  - Network error recovery

- [ ] **Performance optimization**
  - Lazy loading of appdata
  - Background cache updates
  - Parallel search queries

- [ ] **Testing**
  - Unit tests for nix_profile.py
  - Unit tests for nixpkgs_appdata.py
  - Integration tests with PackageKit
  - Mock backend for CI/CD

### Medium Priority

- [ ] **Multi-architecture support**
  - Detect system architecture
  - Download appropriate appdata (aarch64, x86_64, etc.)
  - Handle cross-architecture packages

- [ ] **Configuration file support**
  - Read settings from nix-profile.conf
  - Allow custom appdata URLs
  - Configurable cache behavior

- [ ] **License handling**
  - Parse and categorize licenses from appdata
  - Filter by free/non-free
  - Display license information

- [ ] **Category improvements**
  - Better category mapping
  - Support for custom categories
  - Hierarchical categories

### Low Priority

- [ ] **Icon caching**
  - Download and cache package icons locally
  - Serve icons to software centers
  - Handle different icon sizes

- [ ] **Screenshot support**
  - Parse screenshot data from appdata
  - Provide screenshot URLs
  - Cache screenshots locally

- [ ] **Changelog parsing**
  - Extract changelog information
  - Display update details
  - Link to upstream changelogs

## Phase 3: Advanced Features (Future)

### Nix Integration

- [ ] **Flake support**
  - Install from custom flakes
  - Support flake inputs
  - Handle flake.lock

- [ ] **Generation management**
  - List profile generations
  - Rollback to previous generations
  - Clean old generations

- [ ] **Profile switching**
  - Support multiple profiles
  - Switch between profiles
  - Profile templates

- [ ] **Build options**
  - Support for build flags
  - Override package attributes
  - Custom build configurations

### PackageKit Features

- [ ] **Dependency information**
  - Extract runtime dependencies
  - Show dependency tree
  - Handle circular dependencies

- [ ] **File lists**
  - List files in packages
  - Search by file path
  - File ownership queries

- [ ] **What provides**
  - Search packages by provided files
  - Binary name to package mapping
  - Library provides

- [ ] **Repository management**
  - Add/remove custom repositories
  - Repository priorities
  - Repository metadata

### Software Center Integration

- [ ] **AppStream integration**
  - Full AppStream XML support
  - SPDX license parsing
  - Component metadata

- [ ] **Rating and reviews**
  - Integration with review services
  - Local rating storage
  - Review submission

- [ ] **Update notifications**
  - Desktop notifications for updates
  - Security update highlighting
  - Update scheduling

## Phase 4: Standalone Project

- [ ] **Project separation**
  - Move to separate git repository
  - Independent release cycle
  - Own issue tracker

- [ ] **Packaging**
  - Nix flake for easy installation
  - NixOS module
  - systemd service for cache updates

- [ ] **CI/CD**
  - Automated testing
  - Release automation
  - Documentation generation

- [ ] **Community**
  - Contribution guidelines
  - Code of conduct
  - Community channels (Discord/Matrix)

## Known Issues

### Critical

- None currently

### Major

- Version detection from store paths is heuristic-based
- Complex package names may not parse correctly
- No network timeout handling in appdata download

### Minor

- Progress reporting is approximate
- Some appdata fields not utilized
- Error messages could be more helpful

## Technical Debt

- [ ] Type hints throughout codebase
- [ ] Comprehensive docstrings
- [ ] Code style consistency (black/isort)
- [ ] Logging instead of print statements
- [ ] Configuration file parsing
- [ ] Better separation of concerns

## Documentation Needs

- [ ] Architecture diagram
- [ ] API documentation
- [ ] Development guide
- [ ] Contributing guide
- [ ] FAQ
- [ ] Troubleshooting guide (extended)

## Performance Benchmarks

Current performance (approximate):

- Profile parsing: ~10ms for 50 packages
- Appdata search: ~50ms for simple queries
- Package install: 30s-5min (depends on package)
- Cache refresh: ~1-2 minutes

Target improvements:

- Appdata search: <20ms
- Better install progress tracking
- Incremental cache updates

## Research Areas

- [ ] Investigate nix daemon integration
- [ ] Explore nix-store queries for better metadata
- [ ] Study other package managers' backends
- [ ] Research nix profile internals
- [ ] Investigate nix evaluation for package info

## Breaking Changes (Planned)

None planned for v1.0. After v1.0:

- May change package ID format
- May require newer Nix versions
- Configuration file format may change

## Contributions Welcome

Priority areas for contributors:

1. **Testing**: Unit tests, integration tests
2. **Documentation**: Tutorials, examples
3. **Features**: Version comparison, error handling
4. **Performance**: Query optimization, caching
5. **Integration**: Software center testing

## Upstream Coordination

Coordination needed with:

- **PackageKit**: Ensure API compatibility
- **snowfallorg/nix-software-center**: Appdata format
- **NixOS**: Integration with NixOS ecosystem
- **Software Centers**: GNOME Software, Discover testing

## Success Metrics

- [ ] Install and list 100+ packages successfully
- [ ] Support all major software centers (GNOME Software, Discover)
- [ ] <100ms search queries
- [ ] 90%+ package metadata coverage
- [ ] Positive user feedback from 50+ users

---

Last updated: 2025-01-01
