"""Memoriq SessionEnd hook — runs when Claude Code session ends."""

import json
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

MEMORIQ_HOME = Path.home() / ".memoriq"
DB_PATH = MEMORIQ_HOME / "memory.db"
ACTIVE_SESSION_FILE = MEMORIQ_HOME / "active_session.json"
SESSIONS_DIR = MEMORIQ_HOME / "sessions"
LOG_PATH = MEMORIQ_HOME / "logs" / "memoriq.log"

# Import i18n
sys.path.insert(0, str(MEMORIQ_HOME / "mcp-server"))
try:
    from i18n import t
except ImportError:
    def t(key, **kwargs):
        return key


def open_db():
    from db import open_db_fast
    return open_db_fast()


def read_claude_session_id() -> str | None:
    """Read claude_session_id from stdin (Claude Code hook protocol)."""
    try:
        raw = sys.stdin.buffer.read()
        if raw:
            data = json.loads(raw.decode("utf-8"))
            return data.get("session_id", "")
    except Exception:
        pass
    return None


def read_session_info(claude_session_id: str | None):
    """Read session info from per-session file, fallback to legacy active_session.json."""
    # Try per-session file first
    if claude_session_id:
        session_file = SESSIONS_DIR / f"{claude_session_id}.json"
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                return data.get("session_id", ""), data.get("project", ""), session_file
            except Exception:
                pass

    # Fallback to legacy active_session.json
    if ACTIVE_SESSION_FILE.exists():
        try:
            data = json.loads(ACTIVE_SESSION_FILE.read_text(encoding="utf-8"))
            return data.get("session_id", ""), data.get("project", ""), None
        except Exception:
            pass
    return "", "", None


def build_emergency_bridge(db, session_id: str) -> str:
    changed_files = db.execute("""
        SELECT DISTINCT file_path, action FROM changes
        WHERE session_id = ? ORDER BY timestamp
    """, (session_id,)).fetchall()

    facts = db.execute("""
        SELECT type, substr(content, 1, 80) FROM facts
        WHERE session_id = ? ORDER BY timestamp
    """, (session_id,)).fetchall()

    lines = [t("session_end.emergency_header")]

    if changed_files:
        file_list = ", ".join(f"{f[0]} ({f[1]})" for f in changed_files[:10])
        lines.append(f"Files: {file_list}")
        if len(changed_files) > 10:
            lines.append(t("session_end.and_more", count=len(changed_files) - 10))

    if facts:
        facts_summary = "; ".join(f"[{f[0]}] {f[1]}" for f in facts[:5])
        lines.append(f"Facts: {facts_summary}")

    if not changed_files and not facts:
        lines.append(t("session_end.no_changes"))

    return "\n".join(lines)


def build_episode(db, session_id: str, project: str):
    """Build episode metadata from session facts and changes."""
    try:
        # Gather fact types and domains for this session
        fact_rows = db.execute("""
            SELECT type, domain, tags FROM facts
            WHERE session_id = ?
        """, (session_id,)).fetchall()

        changes_rows = db.execute("""
            SELECT action, file_path FROM changes
            WHERE session_id = ?
        """, (session_id,)).fetchall()

        if not fact_rows and not changes_rows:
            return  # Nothing to build episode from

        # Collect types and domains
        fact_types = {}
        domains = set()
        all_tags = set()
        for row in fact_rows:
            ftype = row[0]
            fact_types[ftype] = fact_types.get(ftype, 0) + 1
            if row[1]:
                domains.add(row[1])
            if row[2]:
                for tag in row[2].split(","):
                    tag = tag.strip()
                    if tag:
                        all_tags.add(tag)

        # Generate episode title
        dominant_type = max(fact_types, key=fact_types.get) if fact_types else None
        type_labels = {
            "error_fix": "Bug fix", "gotcha": "Gotcha discovery",
            "decision": "Decision", "pattern": "Pattern",
            "procedure": "Procedure", "fact": "Knowledge",
            "api_contract": "API contract", "dependency": "Dependency",
            "performance": "Performance", "command": "Command",
            "skill": "Skill", "issue": "Issue", "task": "Task",
            "client_rule": "Client rule",
        }
        title_prefix = type_labels.get(dominant_type, "Session") if dominant_type else "Session"

        # Add domain context to title
        if domains:
            title = f"{title_prefix}: {', '.join(sorted(domains)[:3])}"
        elif changes_rows:
            # Use file extensions as context
            exts = set()
            for row in changes_rows:
                path = row[1]
                if "." in path:
                    exts.add(path.rsplit(".", 1)[-1])
            if exts:
                title = f"{title_prefix}: {', '.join(sorted(exts)[:3])} files"
            else:
                title = f"{title_prefix}: {len(changes_rows)} changes"
        else:
            title = title_prefix

        # Derive episode tags (domains + fact tags, deduplicated)
        episode_tags = sorted(domains | all_tags)[:10]
        tags_str = ", ".join(episode_tags) if episode_tags else None

        # Classify outcome
        outcome = "exploratory"  # default
        if "error_fix" in fact_types or "gotcha" in fact_types:
            outcome = "debugging"
        elif "decision" in fact_types:
            outcome = "planning"
        elif "pattern" in fact_types or "procedure" in fact_types:
            outcome = "productive"
        elif len(changes_rows) > 3 and len(fact_rows) <= 1:
            outcome = "maintenance"

        db.execute("""
            UPDATE sessions SET episode_title = ?, episode_tags = ?, outcome = ?
            WHERE id = ?
        """, (title[:200], tags_str, outcome, session_id))
    except Exception as e:
        sys.stderr.write(f"Memoriq build_episode error: {e}\n")


def log_session_end(project: str, session_id: str, changes: int, facts: int):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} SessionEnd project={project} "
                    f"session={session_id[:8]} changes={changes} facts={facts}\n")
    except Exception:
        pass


def cleanup_old_sessions(db):
    """Remove per-session files for sessions already closed in DB."""
    if not SESSIONS_DIR.exists():
        return
    try:
        for f in SESSIONS_DIR.iterdir():
            if not f.name.endswith(".json"):
                continue
            claude_sid = f.stem
            row = db.execute(
                "SELECT end_time FROM sessions WHERE claude_session_id = ?",
                (claude_sid,)
            ).fetchone()
            # If session is closed (has end_time) or unknown, remove the file
            if row and row[0]:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass


def main():
    if not DB_PATH.exists():
        return

    claude_session_id = read_claude_session_id()
    session_id, project_name, session_file = read_session_info(claude_session_id)
    if not session_id:
        return

    db = open_db()
    try:
        now = datetime.now().isoformat()
        db.execute("UPDATE sessions SET end_time = ? WHERE id = ?", (now, session_id))

        changes_count = db.execute(
            "SELECT COUNT(*) FROM changes WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

        facts_count = db.execute(
            "SELECT COUNT(*) FROM facts WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

        db.execute("""
            UPDATE sessions SET changes_count = ?, facts_count = ? WHERE id = ?
        """, (changes_count, facts_count, session_id))

        row = db.execute(
            "SELECT bridge_content FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        existing_bridge = row[0] if row else None

        if not existing_bridge:
            emergency_bridge = build_emergency_bridge(db, session_id)
            db.execute("UPDATE sessions SET bridge_content = ? WHERE id = ?",
                       (emergency_bridge, session_id))

        log_session_end(project_name, session_id, changes_count, facts_count)

        # Build episode metadata from session activity
        build_episode(db, session_id, project_name)

        # Cleanup old session files (moved from session_start for faster startup)
        cleanup_old_sessions(db)

        db.commit()
    except Exception as e:
        sys.stderr.write(f"Memoriq SessionEnd error: {e}\n")
    finally:
        db.close()

    # Cleanup per-session file
    if session_file:
        try:
            session_file.unlink(missing_ok=True)
        except Exception:
            pass

    # Also try to cleanup legacy active_session.json if it matches this session
    try:
        if ACTIVE_SESSION_FILE.exists():
            data = json.loads(ACTIVE_SESSION_FILE.read_text(encoding="utf-8"))
            if data.get("session_id") == session_id:
                ACTIVE_SESSION_FILE.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
