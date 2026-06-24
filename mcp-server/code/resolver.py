"""Reference resolver — links references to concrete symbols with confidence scoring."""

from __future__ import annotations

import logging
import sqlite3
import time

_log = logging.getLogger("memoriq.code.resolver")


def resolve_references(db: sqlite3.Connection, project: str,
                       time_budget: float = 10.0) -> int:
    """Resolve unlinked references to symbols.

    Matches code_references.to_name against code_symbols.name or qualified_name.
    Updates code_references.to_symbol_id and confidence.

    Returns number of newly resolved references.
    """
    resolved = 0

    # Get all unresolved references for this project
    unresolved = db.execute("""
        SELECT r.id, r.to_name, r.kind, r.file_id, r.from_symbol_id
        FROM code_references r
        WHERE r.project = ? AND r.to_symbol_id IS NULL
    """, (project,)).fetchall()

    if not unresolved:
        return 0

    # Build a lookup of all symbols for this project
    symbols = db.execute("""
        SELECT s.id, s.name, s.qualified_name, s.kind, s.file_id
        FROM code_symbols s
        WHERE s.project = ?
    """, (project,)).fetchall()

    # Index by name and qualified_name
    by_name: dict[str, list[dict]] = {}
    by_qname: dict[str, dict] = {}
    for sym in symbols:
        s = dict(sym)
        name = s["name"]
        qname = s["qualified_name"]
        by_name.setdefault(name, []).append(s)
        by_qname[qname] = s

    start = time.monotonic()

    for ref in unresolved:
        if time.monotonic() - start > time_budget:
            _log.info("Resolver time budget exhausted (%ss), resolved %d/%d",
                      time_budget, resolved, len(unresolved))
            break

        ref_dict = dict(ref)
        to_name = ref_dict["to_name"]
        ref_kind = ref_dict["kind"]

        match = None
        confidence = 0.5

        # Strategy 1: Exact qualified_name match (highest confidence)
        if to_name in by_qname:
            match = by_qname[to_name]
            confidence = 0.95

        # Strategy 2: Dotted name — try last part as name in same file
        if not match and "." in to_name:
            parts = to_name.split(".")
            short_name = parts[-1]
            if short_name in by_name:
                candidates = by_name[short_name]
                # Prefer symbol in same file
                same_file = [c for c in candidates if c["file_id"] == ref_dict["file_id"]]
                if same_file:
                    match = same_file[0]
                    confidence = 0.85
                elif len(candidates) == 1:
                    match = candidates[0]
                    confidence = 0.8
                else:
                    # Multiple candidates — pick best by kind match
                    match = _best_match(candidates, ref_kind)
                    confidence = 0.7

        # Strategy 3: Simple name match
        if not match and to_name in by_name:
            candidates = by_name[to_name]
            # Prefer symbol in same file
            same_file = [c for c in candidates if c["file_id"] == ref_dict["file_id"]]
            if same_file:
                match = same_file[0]
                confidence = 0.85
            elif len(candidates) == 1:
                match = candidates[0]
                confidence = 0.8
            else:
                match = _best_match(candidates, ref_kind)
                confidence = 0.7

        if match:
            try:
                db.execute("""
                    UPDATE code_references SET to_symbol_id = ?, confidence = ?
                    WHERE id = ?
                """, (match["id"], confidence, ref_dict["id"]))
                resolved += 1
            except sqlite3.OperationalError:
                pass  # Skip on lock

    if resolved:
        try:
            db.commit()
        except sqlite3.OperationalError:
            _log.warning("Failed to commit reference resolution")

    return resolved


def _best_match(candidates: list[dict], ref_kind: str) -> dict:
    """Pick best symbol match based on reference kind."""
    # Map reference kinds to preferred symbol kinds
    kind_prefs = {
        "call": ("function", "method"),
        "import": ("function", "class", "variable", "module"),
        "inherit": ("class", "interface"),
        "implement": ("interface",),
        "type_ref": ("interface", "type_alias", "class", "enum"),
        "decorator": ("function",),
    }

    prefs = kind_prefs.get(ref_kind, ())
    for pref in prefs:
        for c in candidates:
            if c["kind"] == pref:
                return c

    return candidates[0]
