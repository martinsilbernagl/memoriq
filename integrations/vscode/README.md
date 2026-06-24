# Memoriq VSCode Extension

Persistent memory and code intelligence for AI coding agents, now in your IDE.

## Features

- **Search Memory**: Quick pick search with preview
- **Write Fact**: Input box for new fact
- **Show Context**: Inline panel with related facts
- **Index Project**: Run code_index on current project
- **Facts Explorer**: Browse facts in sidebar

## Requirements

- VSCode 1.85.0 or higher
- Memoriq MCP server installed (`~/.memoriq/mcp-server/server.py`)
- Python 3.11+

## Installation

1. Build the extension:
```bash
cd integrations/vscode
npm install
npm run compile
```

2. Package or run in development mode:
```bash
# Development mode
code --extensionDevelopmentPath=.

# Or package for distribution
vsce package
```

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| `memoriq.enabled` | Enable Memoriq integration | `true` |
| `memoriq.serverPath` | Path to MCP server | `~/.memoriq/mcp-server/server.py` |
| `memoriq.pythonPath` | Python executable | `python` |
| `memoriq.showInlineHints` | Show inline memory hints | `true` |
| `memoriq.autoIndex` | Auto-index on project open | `false` |

## Commands

| Command | Description |
|---------|-------------|
| `Memoriq: Search Memory` | Search facts by query |
| `Memoriq: Write Fact` | Write a new fact |
| `Memoriq: Show Context` | Get code context for symbol |
| `Memoriq: Index Project` | Index current project |
| `Memoriq: Browse Facts` | Open facts explorer |

## Development

This is a skeleton implementation. Full MCP client functionality requires:

1. Complete MCP SDK integration
2. Proper response parsing from MCP tools
3. Enhanced tree view with fact details
4. Inline hints provider

## License

MIT
