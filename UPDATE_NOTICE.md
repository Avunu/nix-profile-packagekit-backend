# Update Notice - Corrected Data Sources

## Changes Made

The backend implementation has been **updated to use the correct snowfallorg data sources**:

### Previous (Incorrect)
- ❌ Downloaded from `snowfallorg/nix-software-center` releases
- ❌ Expected YAML appdata format
- ❌ Built SQLite database from scratch

### Current (Correct)
- ✅ Downloads from **snowfallorg/nix-data-db**
- ✅ Uses pre-built, brotli-compressed SQLite databases
- ✅ Auto-detects channel (nixos-unstable, nixos-23.05, etc.)
- ✅ Faster setup (no database building required)

## Data Sources

### Primary: nix-data-db
- **URL**: https://github.com/snowfallorg/nix-data-db
- **Contains**: Pre-built SQLite databases with package metadata
- **Channels**: nixos-22.05, 22.11, 23.05, unstable, nixpkgs-unstable
- **Size**: ~5-10MB compressed per channel
- **Format**: Brotli-compressed SQLite (.db.br)
- **Schema**: `attribute`, `pname`, `version`, `description`, `homepage`, `license`

### Future: nixos-appstream-data
- **URL**: https://github.com/snowfallorg/nixos-appstream-data
- **Contains**: AppStream XML files with detailed app information
- **Includes**: Icons (64x64, 128x128), screenshots, categories
- **Structure**: `free/` and `unfree/` directories with metadata and icons
- **Not yet integrated**: Will be added in future versions for rich metadata

## Key Implementation Changes

### nixpkgs_appdata.py
1. **Channel detection**: Auto-detects NixOS/nixpkgs channel from system
2. **Direct downloads**: Downloads .db.br files from GitHub raw URLs
3. **Brotli decompression**: Decompresses databases (requires `brotli` package)
4. **Updated queries**: Uses actual nix-data-db schema (`attribute`, `pname` columns)
5. **Removed YAML parsing**: No longer needed

### Dependencies
- **Removed**: `pyyaml`
- **Added**: `brotli` (for database decompression)

### Configuration
- Updated to reflect correct repositories
- Added channel configuration option

## Benefits

1. **Faster**: Pre-built databases, no parsing/building needed
2. **Smaller**: ~5-10MB vs ~50MB downloads
3. **More reliable**: Official snowfallorg data infrastructure
4. **Better maintained**: Regularly updated via GitHub Actions
5. **Accurate**: Uses actual nix-data-db schema

## Migration

No migration needed! Just:
```bash
# Install new dependency
pip install brotli

# Refresh cache (will download correct database)
pkcon refresh --force
```

Old cache files will be ignored automatically.

## Future Roadmap

### Phase 1 (Current)
- ✅ Use nix-data-db for basic package metadata
- ✅ Search by name and description
- ✅ Display versions, descriptions, homepages, licenses

### Phase 2 (Next)
- ⏳ Parse nixos-appstream-data XML files
- ⏳ Extract application icons and screenshots
- ⏳ Category-based browsing
- ⏳ Richer metadata for GUI software centers

### Phase 3 (Future)
- ⏳ Icon caching and serving
- ⏳ Screenshot URLs
- ⏳ Better license categorization (free/unfree)
- ⏳ Desktop file integration

## References

- **nix-data-db**: https://github.com/snowfallorg/nix-data-db
- **nixos-appstream-data**: https://github.com/snowfallorg/nixos-appstream-data
- **nix-data-generator**: https://github.com/snowfallorg/nix-data-generator (generates the databases)
- **nixos-appstream-generator**: https://github.com/snowfallorg/nixos-appstream-generator (generates AppStream data)

---

**Note**: nix-software-center is a consumer/example implementation, not a data provider. The actual data comes from the specialized repositories listed above.
