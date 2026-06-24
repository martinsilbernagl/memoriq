"""memory_chain — Create causal chain links between facts in Memoriq memory."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db import open_db
from utils import get_active_session
from i18n import t

VALID_RELATIONSHIPS = ("caused", "led_to", "blocked", "fixed", "broke")


def memory_chain(cause_id: str, effect_id: str,
                 relationship: str = "caused") -> str:
    """Create a causal chain link between two facts."""
    if cause_id == effect_id:
        return t("memory_chain.self_chain")

    if relationship not in VALID_RELATIONSHIPS:
        return t("memory_chain.invalid_relationship",
                 relationship=relationship,
                 valid=", ".join(VALID_RELATIONSHIPS))

    session = get_active_session()
    project = session.get("project", "")
    session_id = session.get("session_id")

    db = open_db()
    try:
        # Validate both facts exist and belong to same project
        cause = db.execute(
            "SELECT id, content, project FROM facts WHERE id = ?", (cause_id,)
        ).fetchone()
        if not cause:
            return t("memory_chain.not_found", id=cause_id)

        effect = db.execute(
            "SELECT id, content, project FROM facts WHERE id = ?", (effect_id,)
        ).fetchone()
        if not effect:
            return t("memory_chain.not_found", id=effect_id)

        if cause[2] != effect[2]:
            return t("memory_chain.cross_project",
                     cause_project=cause[2], effect_project=effect[2])

        # Check for duplicate
        existing = db.execute("""
            SELECT 1 FROM causal_chains
            WHERE cause_id = ? AND effect_id = ?
        """, (cause_id, effect_id)).fetchone()
        if existing:
            return t("memory_chain.already_exists",
                     cause=cause[1][:50], effect=effect[1][:50])

        # Insert causal chain
        now = datetime.now().isoformat()
        db.execute("""
            INSERT INTO causal_chains
                (project, cause_id, effect_id, relationship, confidence, created, session_id)
            VALUES (?, ?, ?, ?, 1.0, ?, ?)
        """, (cause[2], cause_id, effect_id, relationship, now, session_id))

        db.commit()
    finally:
        db.close()

    return t("memory_chain.created",
             cause=cause[1][:50], effect=effect[1][:50],
             relationship=relationship)
