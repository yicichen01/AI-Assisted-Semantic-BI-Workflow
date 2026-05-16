"""
SQLite persistence layer for the AI-Assisted Semantic BI Workflow.

All public functions are wrapped in try/except and return safe fallbacks on failure.
Errors are logged at WARNING level only — never exposed to the UI.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = PROJECT_ROOT / "data" / "bi_workflow.db"

# Ensure the data/ directory exists at import time (non-fatal)
try:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
except Exception as _exc:
    logger.warning("db_service: could not create data/ directory: %s", _exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_list(value) -> str:
    """Serialize a list to JSON string; pass through non-list values."""
    if isinstance(value, list):
        return json.dumps(value)
    if value is None:
        return json.dumps([])
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> bool:
    """Create tables if they don't exist. Return True on success, False on failure."""
    try:
        conn = _get_connection()
        cur = conn.cursor()

        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT,
                domain_name TEXT,
                role TEXT,
                semantic_mode TEXT,
                max_questions INTEGER,
                dataset_rows INTEGER,
                dataset_fields INTEGER,
                generated_questions INTEGER,
                verified_count INTEGER,
                review_count INTEGER,
                reject_count INTEGER,
                average_score REAL
            );

            CREATE TABLE IF NOT EXISTS promotion_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                question_text TEXT,
                promotion_status TEXT,
                guardrail_category TEXT,
                final_score REAL,
                promotion_reason TEXT,
                suggested_fix TEXT,
                deal_breakers TEXT,
                easy_to_fix_items TEXT,
                ambiguity_flags TEXT,
                target_metrics TEXT,
                target_dimensions TEXT,
                time_grain TEXT
            );

            CREATE TABLE IF NOT EXISTS review_decisions (
                decision_id TEXT PRIMARY KEY,
                created_at TEXT,
                run_id TEXT,
                original_question TEXT,
                revised_question TEXT,
                original_status TEXT,
                action TEXT,
                guardrail_category TEXT,
                suggested_fix TEXT,
                reviewer_note TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                created_at TEXT,
                event_type TEXT,
                role TEXT,
                domain_name TEXT,
                run_id TEXT,
                message TEXT
            );
            """
        )

        conn.commit()
        conn.close()
        return True

    except Exception as exc:
        logger.warning("db_service.init_db failed: %s", exc)
        return False


def save_pipeline_run(
    domain_name: str,
    role: str,
    semantic_mode: str,
    max_questions: int,
    dataset_rows: int,
    dataset_fields: int,
    promotion_results: list,
) -> Optional[str]:
    """
    Insert one row into pipeline_runs and N rows into promotion_results.
    Also insert an audit_event with event_type='pipeline_run'.
    Return run_id (str uuid4) on success, None on failure.
    """
    try:
        run_id = str(uuid.uuid4())
        created_at = _now_iso()

        # Compute summary stats from promotion_results
        generated_questions = len(promotion_results)
        verified_count = sum(
            1 for r in promotion_results if r.get("promotion_status") == "verified"
        )
        review_count = sum(
            1 for r in promotion_results if r.get("promotion_status") == "review"
        )
        reject_count = sum(
            1 for r in promotion_results if r.get("promotion_status") == "reject"
        )

        scores = [
            float(r["final_score"])
            for r in promotion_results
            if r.get("final_score") is not None
        ]
        average_score = sum(scores) / len(scores) if scores else 0.0

        conn = _get_connection()
        cur = conn.cursor()

        # Insert pipeline_runs row
        cur.execute(
            """
            INSERT INTO pipeline_runs (
                run_id, created_at, domain_name, role, semantic_mode,
                max_questions, dataset_rows, dataset_fields,
                generated_questions, verified_count, review_count,
                reject_count, average_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, created_at, domain_name, role, semantic_mode,
                max_questions, dataset_rows, dataset_fields,
                generated_questions, verified_count, review_count,
                reject_count, average_score,
            ),
        )

        # Insert promotion_results rows
        for r in promotion_results:
            cur.execute(
                """
                INSERT INTO promotion_results (
                    run_id, question_text, promotion_status, guardrail_category,
                    final_score, promotion_reason, suggested_fix,
                    deal_breakers, easy_to_fix_items, ambiguity_flags,
                    target_metrics, target_dimensions, time_grain
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    r.get("question_text"),
                    r.get("promotion_status"),
                    r.get("guardrail_category"),
                    r.get("final_score"),
                    r.get("promotion_reason"),
                    r.get("suggested_fix"),
                    _serialize_list(r.get("deal_breakers")),
                    _serialize_list(r.get("easy_to_fix_items")),
                    _serialize_list(r.get("ambiguity_flags")),
                    _serialize_list(r.get("target_metrics")),
                    _serialize_list(r.get("target_dimensions")),
                    r.get("time_grain"),
                ),
            )

        # Insert audit event
        cur.execute(
            """
            INSERT INTO audit_events (event_id, created_at, event_type, role, domain_name, run_id, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                created_at,
                "pipeline_run",
                role,
                domain_name,
                run_id,
                (
                    f"Pipeline run completed: {generated_questions} questions generated, "
                    f"{verified_count} verified, {review_count} review, {reject_count} reject."
                ),
            ),
        )

        conn.commit()
        conn.close()
        return run_id

    except Exception as exc:
        logger.warning("db_service.save_pipeline_run failed: %s", exc)
        return None


def save_review_decision(
    run_id: Optional[str],
    decision: dict,
    role: str,
    domain_name: str,
) -> bool:
    """
    Insert one row into review_decisions and one audit_event with
    event_type='review_decision'.
    Return True on success, False on failure.
    """
    try:
        decision_id = str(uuid.uuid4())
        created_at = _now_iso()

        conn = _get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO review_decisions (
                decision_id, created_at, run_id,
                original_question, revised_question, original_status,
                action, guardrail_category, suggested_fix, reviewer_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                created_at,
                run_id,
                decision.get("original_question"),
                decision.get("revised_question"),
                decision.get("original_status"),
                decision.get("action"),
                decision.get("guardrail_category"),
                decision.get("suggested_fix"),
                decision.get("reviewer_note"),
            ),
        )

        cur.execute(
            """
            INSERT INTO audit_events (event_id, created_at, event_type, role, domain_name, run_id, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                created_at,
                "review_decision",
                role,
                domain_name,
                run_id,
                (
                    f"Review decision '{decision.get('action')}' applied to: "
                    f"{decision.get('original_question', '')[:80]}"
                ),
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception as exc:
        logger.warning("db_service.save_review_decision failed: %s", exc)
        return False


def log_audit_event(
    event_type: str,
    role: str,
    domain_name: str,
    run_id: Optional[str],
    message: str,
) -> bool:
    """Insert one row into audit_events. Return True on success, False on failure."""
    try:
        conn = _get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO audit_events (event_id, created_at, event_type, role, domain_name, run_id, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                _now_iso(),
                event_type,
                role,
                domain_name,
                run_id,
                message,
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception as exc:
        logger.warning("db_service.log_audit_event failed: %s", exc)
        return False


def get_recent_runs(n: int = 20) -> list:
    """Return last n rows from pipeline_runs ordered by created_at DESC as list of dicts."""
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
            (n,),
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    except Exception as exc:
        logger.warning("db_service.get_recent_runs failed: %s", exc)
        return []


def get_audit_events(n: int = 50) -> list:
    """Return last n rows from audit_events ordered by created_at DESC as list of dicts."""
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
            (n,),
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    except Exception as exc:
        logger.warning("db_service.get_audit_events failed: %s", exc)
        return []


def get_review_decisions(run_id: Optional[str] = None) -> list:
    """
    Return review_decisions as list of dicts.
    If run_id is provided, filter by run_id.
    Order by created_at DESC. Limit 100.
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()

        if run_id is not None:
            cur.execute(
                "SELECT * FROM review_decisions WHERE run_id = ? ORDER BY created_at DESC LIMIT 100",
                (run_id,),
            )
        else:
            cur.execute(
                "SELECT * FROM review_decisions ORDER BY created_at DESC LIMIT 100"
            )

        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    except Exception as exc:
        logger.warning("db_service.get_review_decisions failed: %s", exc)
        return []


def get_db_status() -> dict:
    """
    Return {"enabled": bool, "path": str, "run_count": int}.
    enabled=False if DB is not accessible.
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pipeline_runs")
        run_count = cur.fetchone()[0]
        conn.close()
        return {
            "enabled": True,
            "path": str(_DB_PATH),
            "run_count": run_count,
        }

    except Exception as exc:
        logger.warning("db_service.get_db_status failed: %s", exc)
        return {
            "enabled": False,
            "path": str(_DB_PATH),
            "run_count": 0,
        }
