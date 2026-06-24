# Upgrade na Memoriq v5.0

## Rychlý upgrade (30 sekund)

```bash
cd /root/projekty/Memoriq

# 1. Stáhni nejnovější změny
git pull

# 2. Spusť instalaci s wizardem (doporučeno)
python install.py --wizard

# 3. Restartuj Claude Code
# (ukonči a spusť znovu)
```

## Co se změní

### Automaticky (bez zásahu)
- Databáze se automaticky migruje (záloha se vytvoří)
- Nové tabulky a sloupce se přidají
- MCP server se zaregistruje s 23 nástroji

### Ruční konfigurace (volitelné)
- Nové integrace v `~/.memoriq/config.yaml` (Obsidian, webhooks)
- Performance nastavení (caching, pooling)

## Ověření instalace

```bash
# Test MCP serveru
python ~/.memoriq/mcp-server/server.py --test
# → "OK: All 23 tools registered."

# Test TUI
memoriq --demo

# Test wizardu (pokud chceš znovu spustit)
python install.py --wizard
```

## Nové příkazy po upgradu

V Claude Code:
- `/setup-checklist` - Ověření instalace
- `/status` - Statistiky paměti

Nové MCP nástroje:
- `memory_stats()` - Statistiky paměti
- `memory_export()` - Export do JSON/Markdown
- `code_dependencies()` - Graf závislostí
- `code_refactor_suggest()` - Návrhy refactoringu
- `fact_compare()` - Porovnání faktů

## Rollback (pokud něco nefunguje)

```bash
# Obnovení databáze ze zálohy
cp ~/.memoriq/memory.db.backup-* ~/.memoriq/memory.db

# Návrat na starou verzi
git checkout dc8820f  # v4.2.0
python install.py
```
