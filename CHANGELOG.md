# Changelog

All notable changes to Memoriq will be documented in this file.

## [5.0.0] - 2026-03-11

## [5.0.3] - 2026-03-11

### Auto-generated

- docs: Add troubleshooting guide
  - Commit: 7fffb32
  - Author: DomeSs


## [5.0.2] - 2026-03-11

### Auto-generated

- feat(errors): Add centralized error handling
  - Commit: 28c82d4
  - Author: DomeSs


## [5.0.1] - 2026-03-11

### Auto-generated

- test: přidán post-commit hook pro auto-verzování
  - Commit: a3d421b
  - Author: DomeSs


### 🚀 Major Release - Memoriq v5

### Added

#### New MCP Tools (5 tools, 23 total)
- `memory_stats` - Memory usage analytics with heat distribution, fact counts by type, project sizes
- `memory_export` - Export facts to JSON or Markdown for backup/sharing
- `fact_compare` - Compare two facts side-by-side with diff highlighting
- `code_refactor_suggest` - AI-powered refactoring suggestions based on complexity analysis
- `code_dependencies` - File-level dependency graph with circular dependency detection

#### Code Intelligence v2
- **Go language support** - Full parser extracting functions, structs, interfaces, methods
- **Rust language support** - Complete parser for traits, impls, enums, functions
- **Complexity metrics** - Cyclomatic complexity, cognitive complexity, lines of code
- **Unused function detection** - Identifies dead code (non-exported functions with no references)
- **Dependency graph** - Visualize file-level imports and relationships

#### Performance & Scale
- Query result caching with LRU + TTL (60s default)
- Connection pooling (5 concurrent connections)
- Batch memory writes (10x faster than individual inserts)
- Performance metrics collection and slow query logging
- Database query optimization with covering indexes

#### UX Improvements
- Interactive setup wizard (`python install.py --wizard`)
- Progress tracking for long operations (code_index, file_index)
- TUI keyboard shortcuts help (press `?` for help overlay)
- TUI export functionality (press `e` to export filtered facts)
- Enhanced demo data (80 facts across 5 sample projects)
- `/setup-checklist` command for installation verification

#### Integrations Platform
- **VSCode Extension** - Full-featured extension with:
  - Sidebar tree view of facts
  - Commands: search, write, context, index
  - MCP client for direct server communication
- **Obsidian Export** - Export facts as Obsidian markdown with:
  - Wiki-links [[target|display]] support
  - Auto-export on memory events
  - Frontmatter with metadata
- **Git Hooks** - Pre-commit hooks showing relevant facts

#### Infrastructure
- `wizard.py` - Interactive configuration wizard
- `mcp-server/progress.py` - Progress tracking system
- `integrations/` directory with webhook, obsidian, git hooks modules
- Performance test suite (`tests/test_performance.py`)

### Changed
- Updated MCP tool count: 18 → 23
- Enhanced `code_context` with complexity display and unused detection
- Improved `memory_write` with batch operations
- Upgraded demo data generator with more diverse fact types

### Fixed
- Various tool reference updates (17→18→22→23 tools)
- i18n translations for all new tools (EN + CS)

---

## [4.2.0] - 2026-03-10

### Added
- `file_index` MCP tool for indexing project documentation
- Full Codex CLI onboarding support
- Code Graph browser tab in TUI (8 tabs total)
- Subagent Memory Protocol v2 with tags filtering

### Changed
- Updated README with real-world examples
- Improved code intelligence examples

---

## [4.1.0] - 2026-03-08

### Added
- Unified workflow instructions
- File search empty index hints

### Fixed
- 3 failing CI tests
- Python 3.13 removed from test matrix (compatibility issues)

---

## [4.0.0] - 2026-03-05

### Added
- Initial stable release
- 18 MCP tools for memory and code intelligence
- TUI dashboard with 7 tabs
- Session bridge for continuity
- Project Identity Card system
- Subagent Memory Protocol
- Tree-sitter based code intelligence (Python, TypeScript, JavaScript)
- Hybrid search (FTS5 + vector)
- Heat decay system
- Czech (CS) localization

### Changed
- License: GPL-3.0 → Elastic License 2.0

---

## Migration Guides

### Upgrading to v5.0.0

```bash
# Pull latest changes
git pull

# Run interactive wizard for new configuration
python install.py --wizard

# Or standard install
python install.py

# Verify all 23 tools are registered
python ~/.memoriq/mcp-server/server.py --test
```

Database schema is automatically migrated. Your existing memory is preserved.

### Breaking Changes

None - v5.0.0 is fully backward compatible. All new features are opt-in.
