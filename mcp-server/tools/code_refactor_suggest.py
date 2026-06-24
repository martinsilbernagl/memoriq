"""code_refactor_suggest — Analyze code symbols and suggest refactoring opportunities."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db import open_db
from utils import get_active_session
from i18n import t


def code_refactor_suggest(symbol: str, project_name: str = None) -> str:
    """Analyze a code symbol and suggest refactoring opportunities based on complexity,
    duplication, and code patterns.
    """
    session = get_active_session()
    project = project_name or session.get("project", "")

    if not project:
        return t("code_refactor_suggest.no_project")

    db = open_db()
    try:
        # Find the symbol
        sym = db.execute("""
            SELECT s.id, s.name, s.qualified_name, s.kind, s.line_start, s.line_end,
                   s.signature, s.docstring, f.file_path, f.language,
                   (s.line_end - s.line_start + 1) as line_count
            FROM code_symbols s
            JOIN code_files f ON s.file_id = f.id
            WHERE s.project = ? AND (s.name = ? OR s.qualified_name = ?)
            LIMIT 1
        """, (project, symbol, symbol)).fetchone()

        if not sym:
            return t("code_refactor_suggest.symbol_not_found", symbol=symbol, project=project)

        lines = [t("code_refactor_suggest.header",
                   name=sym['name'], kind=sym['kind'], file=sym['file_path'])]

        suggestions = []
        line_count = sym['line_count']

        # Size-based analysis
        if sym['kind'] == 'function' and line_count > 50:
            suggestions.append({
                'type': 'size',
                'severity': 'high',
                'message': t("code_refactor_suggest.long_function", lines=line_count)
            })
        elif sym['kind'] == 'method' and line_count > 40:
            suggestions.append({
                'type': 'size',
                'severity': 'medium',
                'message': t("code_refactor_suggest.long_method", lines=line_count)
            })
        elif sym['kind'] == 'class' and line_count > 300:
            suggestions.append({
                'type': 'size',
                'severity': 'high',
                'message': t("code_refactor_suggest.large_class", lines=line_count)
            })

        # Reference/coupling analysis
        refs = db.execute("""
            SELECT COUNT(*) as ref_count,
                   COUNT(DISTINCT file_id) as file_count
            FROM code_references
            WHERE to_symbol_id = ? OR (to_name = ? AND to_symbol_id IS NULL)
        """, (sym['id'], sym['name'])).fetchone()

        if refs and refs['ref_count']:
            if refs['ref_count'] > 50:
                suggestions.append({
                    'type': 'coupling',
                    'severity': 'high',
                    'message': t("code_refactor_suggest.high_coupling",
                               count=refs['ref_count'], files=refs['file_count'])
                })
            elif refs['ref_count'] > 20:
                suggestions.append({
                    'type': 'coupling',
                    'severity': 'medium',
                    'message': t("code_refactor_suggest.moderate_coupling",
                               count=refs['ref_count'], files=refs['file_count'])
                })

        # Duplicate detection (same name, similar signature in same project)
        if sym['signature']:
            dups = db.execute("""
                SELECT s.name, s.qualified_name, f.file_path,
                       (s.line_end - s.line_start + 1) as their_lines
                FROM code_symbols s
                JOIN code_files f ON s.file_id = f.id
                WHERE s.project = ? AND s.name = ? AND s.id != ?
                      AND f.file_path != ?
                LIMIT 5
            """, (project, sym['name'], sym['id'], sym['file_path'])).fetchall()

            if dups:
                suggestions.append({
                    'type': 'duplication',
                    'severity': 'medium',
                    'message': t("code_refactor_suggest.possible_duplicates", count=len(dups))
                })
                lines.append("\n" + t("code_refactor_suggest.duplicates_header"))
                for dup in dups:
                    lines.append(f"  - {dup['qualified_name']} in {dup['file_path']}")

        # Parameter count analysis (from signature)
        param_count = 0
        if sym['signature']:
            # Rough estimation: count commas in parameter list
            sig = sym['signature']
            if '(' in sig and ')' in sig:
                params = sig[sig.find('(')+1:sig.rfind(')')]
                if params.strip():
                    param_count = params.count(',') + 1

        if param_count > 5:
            suggestions.append({
                'type': 'parameters',
                'severity': 'medium',
                'message': t("code_refactor_suggest.many_parameters", count=param_count)
            })

        # Output suggestions
        if suggestions:
            lines.append("\n" + t("code_refactor_suggest.suggestions_header"))

            # Sort by severity
            severity_order = {'high': 0, 'medium': 1, 'low': 2}
            suggestions.sort(key=lambda x: severity_order.get(x['severity'], 3))

            for i, sug in enumerate(suggestions, 1):
                icon = "🔴" if sug['severity'] == 'high' else "🟡" if sug['severity'] == 'medium' else "🟢"
                lines.append(f"{i}. {icon} [{sug['type']}] {sug['message']}")
        else:
            lines.append("\n" + t("code_refactor_suggest.no_issues"))

        # Add metrics summary
        lines.append("\n" + t("code_refactor_suggest.metrics"))
        lines.append(f"  Lines: {line_count}")
        lines.append(f"  References: {refs['ref_count'] if refs else 0}")
        lines.append(f"  Used in files: {refs['file_count'] if refs else 0}")
        if param_count:
            lines.append(f"  Parameters: {param_count}")

        return "\n".join(lines)

    finally:
        db.close()
