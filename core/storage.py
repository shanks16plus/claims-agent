"""Claims log, photo hashes and adjuster overrides, in one local SQLite file."""
import json
import secrets
import sqlite3
from datetime import datetime

from core import config

DB_PATH = config.RUNTIME / "claims.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    filed_at TEXT,
    decided_at TEXT,
    channel TEXT,
    policy_number TEXT,
    status TEXT,
    decision TEXT,
    estimate_eur REAL,
    payout_eur REAL,
    fraud_risk TEXT,
    fraud_reasons TEXT,
    confidence REAL,
    chat_turns INTEGER,
    seconds_to_file REAL,
    photo_retakes INTEGER,
    processing_seconds REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    api_cost_eur REAL,
    details TEXT
);
CREATE TABLE IF NOT EXISTS photo_hashes (
    claim_id TEXT,
    source_key TEXT,
    photo TEXT,
    phash TEXT
);
CREATE TABLE IF NOT EXISTS overrides (
    claim_id TEXT,
    at TEXT,
    action TEXT,
    amount_before REAL,
    amount_after REAL,
    note TEXT
);
"""

CLAIM_COLUMNS = [
    "claim_id", "filed_at", "decided_at", "channel", "policy_number", "status", "decision",
    "estimate_eur", "payout_eur", "fraud_risk", "fraud_reasons", "confidence", "chat_turns",
    "seconds_to_file", "photo_retakes", "processing_seconds", "input_tokens", "output_tokens",
    "api_cost_eur", "details",
]


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def now():
    return datetime.now().isoformat(timespec="seconds")


def new_claim_id():
    return f"CLM-{datetime.now():%Y%m%d}-{secrets.token_hex(2).upper()}"


def save_claim(record):
    """Insert or update one claim. Lists and dicts are stored as JSON text."""
    row = {col: record.get(col) for col in CLAIM_COLUMNS}
    for col in ("fraud_reasons", "details"):
        if not isinstance(row[col], str) and row[col] is not None:
            row[col] = json.dumps(row[col], ensure_ascii=False, default=str)
    placeholders = ", ".join("?" for _ in CLAIM_COLUMNS)
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO claims ({', '.join(CLAIM_COLUMNS)}) VALUES ({placeholders})",
            [row[col] for col in CLAIM_COLUMNS],
        )


def get_claim(claim_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if row is None:
        return None
    claim = dict(row)
    for col in ("fraud_reasons", "details"):
        if claim[col]:
            claim[col] = json.loads(claim[col])
    return claim


def save_photo_hashes(claim_id, source_key, hashes):
    """`hashes` is a list of (photo name, perceptual hash)."""
    with connect() as conn:
        conn.executemany(
            "INSERT INTO photo_hashes (claim_id, source_key, photo, phash) VALUES (?, ?, ?, ?)",
            [(claim_id, source_key, photo, phash) for photo, phash in hashes],
        )


def earlier_photo_hashes(exclude_source_key):
    """Photo hashes from other claims. Re-runs of the same demo or test case are skipped,
    and batch-test photos are only compared with other batch-test photos."""
    batch_only = str(exclude_source_key).startswith("batch:")
    with connect() as conn:
        rows = conn.execute(
            "SELECT claim_id, photo, phash FROM photo_hashes "
            "WHERE source_key != ? AND (source_key LIKE 'batch:%') = ?",
            (exclude_source_key, batch_only),
        ).fetchall()
    return [dict(row) for row in rows]


SPEND_DB_PATH = config.RUNTIME / "spend.db"


def _spend_db():
    SPEND_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SPEND_DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS spend (at TEXT, model TEXT, prompt TEXT, cost_eur REAL)")
    return conn


def log_spend(model, prompt, cost_eur):
    with _spend_db() as conn:
        conn.execute("INSERT INTO spend VALUES (?, ?, ?, ?)", (now(), model, prompt, cost_eur))


def total_spend():
    with _spend_db() as conn:
        return conn.execute("SELECT COALESCE(SUM(cost_eur), 0) FROM spend").fetchone()[0]


def log_override(claim_id, action, amount_before, amount_after, note):
    with connect() as conn:
        conn.execute(
            "INSERT INTO overrides (claim_id, at, action, amount_before, amount_after, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (claim_id, now(), action, amount_before, amount_after, note),
        )


def list_claims(statuses=None, since=None, until=None):
    """Claims newest first, optionally filtered by status and by filing date (ISO strings, inclusive)."""
    query, params = "SELECT * FROM claims WHERE 1=1", []
    if statuses:
        query += f" AND status IN ({', '.join('?' for _ in statuses)})"
        params += list(statuses)
    if since:
        query += " AND filed_at >= ?"
        params.append(since)
    if until:
        query += " AND filed_at <= ?"
        params.append(until + "T23:59:59")
    with connect() as conn:
        rows = conn.execute(query + " ORDER BY filed_at DESC", params).fetchall()
    claims = []
    for row in rows:
        claim = dict(row)
        for col in ("fraud_reasons", "details"):
            if claim[col]:
                claim[col] = json.loads(claim[col])
        claims.append(claim)
    return claims


def record_decision(claim_id, status, payout_eur):
    """A claims handler's decision: new status, final payout and the decision time."""
    with connect() as conn:
        conn.execute("UPDATE claims SET status = ?, payout_eur = ?, decided_at = ? WHERE claim_id = ?",
                     (status, payout_eur, now(), claim_id))


def list_overrides(claim_id=None):
    query, params = "SELECT * FROM overrides", []
    if claim_id:
        query, params = query + " WHERE claim_id = ?", [claim_id]
    with connect() as conn:
        return [dict(row) for row in conn.execute(query + " ORDER BY at DESC", params).fetchall()]
