# /setup-checklist

Run this checklist to verify Memoriq is properly set up:

## Installation Check

- [ ] Memoriq files installed at `~/.memoriq/`
- [ ] Database initialized (`memory.db` exists)
- [ ] MCP server registered in Claude Code settings

To verify:
```bash
ls ~/.memoriq/
ls ~/.memoriq/memory.db
```

## Configuration Check

- [ ] `config.yaml` exists and is valid
- [ ] `projects.base_path` points to your projects directory
- [ ] Language preference set (en or cs)

To verify:
```bash
cat ~/.memoriq/config.yaml
```

## Feature Check

- [ ] TUI dashboard works: run `memoriq` in terminal
- [ ] Slash commands available: type `/` in Claude Code
- [ ] MCP tools responding: run `/status`

To test TUI:
```bash
memoriq --demo
```

## First Project Setup

- [ ] Navigate to a project directory
- [ ] Run `/onboard` to build initial memory
- [ ] Run `code_index()` to index source code
- [ ] Run `file_index()` to index documentation

## Verification

- [ ] Run `memory_search(query="test")` - should return results
- [ ] Run `file_search(query="README")` - should find README files
- [ ] Run `code_search(query="main")` - should find main functions

## Troubleshooting

If any check fails:

1. **MCP server not connecting**
   - Restart Claude Code (required after installation)
   - Run: `python ~/.memoriq/diagnose.py --fix`

2. **Tools not found**
   - Check registration: `cat ~/.claude/settings.json | grep memoriq`
   - Re-register: `python ~/.memoriq/install.py`

3. **Database errors**
   - Check permissions: `ls -la ~/.memoriq/memory.db`
   - Reset if needed: `rm ~/.memoriq/memory.db && python ~/.memoriq/install.py`

4. **TUI not launching**
   - Check textual is installed: `python -m pip install textual`
   - Run directly: `python ~/.memoriq/tui/app.py --demo`

## Next Steps

If all checks pass, Memoriq is ready to use!

- Run `/memoriqhelp` to see all available commands
- Press `?` in the TUI to see keyboard shortcuts
- Use `memory_write()` to save important discoveries
- Use `code_context()` to understand code relationships

## Getting Help

- Run diagnostics: `python ~/.memoriq/diagnose.py`
- Check logs: `cat ~/.memoriq/logs/progress.log`
- View memory: `memoriq` (TUI dashboard)
