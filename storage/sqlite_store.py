import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT, company TEXT, job_title TEXT, jd_text TEXT,
    inputs TEXT, original_resume_text TEXT, resume_json TEXT, jd_analysis TEXT, photo BLOB
);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
    version_no INTEGER, created_at TEXT, model TEXT, intensity TEXT, feedback TEXT,
    resume_json TEXT, cover_letter TEXT, ats_before INTEGER, ats_after INTEGER, ats_detail TEXT,
    change_log TEXT, notes TEXT, verification TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL, is_final INTEGER DEFAULT 0
);
-- Kept independent of applications so spend history survives deletes.
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER, version_id INTEGER, company TEXT, step TEXT, model TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL, ts TEXT
);
"""
JSON_COLS = {"inputs", "resume_json", "jd_analysis", "ats_detail", "change_log", "notes", "verification"}
VERSION_COLS = ["model", "intensity", "feedback", "resume_json", "cover_letter", "ats_before", "ats_after",
                "ats_detail", "change_log", "notes", "verification", "prompt_tokens", "completion_tokens", "cost_usd"]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _enc(k, v):
    return json.dumps(v, ensure_ascii=False) if k in JSON_COLS and v is not None else v


def _dec(row) -> dict:
    d = dict(row)
    for k in JSON_COLS & d.keys():
        d[k] = json.loads(d[k]) if d[k] else None
    if "is_final" in d:
        d["is_final"] = bool(d["is_final"])
    return d


class SQLiteStore:
    name = "SQLite (local file)"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_application(self, *, company, job_title, jd_text, inputs, original_resume_text,
                           resume_json, jd_analysis, photo=None) -> int:
        row = dict(created_at=now(), company=company, job_title=job_title, jd_text=jd_text, inputs=inputs,
                   original_resume_text=original_resume_text, resume_json=resume_json,
                   jd_analysis=jd_analysis, photo=photo)
        cols = ", ".join(row)
        with self._conn() as c:
            cur = c.execute(f"INSERT INTO applications ({cols}) VALUES ({', '.join('?' * len(row))})",
                            [_enc(k, v) for k, v in row.items()])
            return cur.lastrowid

    def add_version(self, app_id: int, data: dict) -> int:
        with self._conn() as c:
            n = c.execute("SELECT COALESCE(MAX(version_no), 0) + 1 FROM versions WHERE application_id = ?",
                          (app_id,)).fetchone()[0]
            cols = ["application_id", "version_no", "created_at"] + VERSION_COLS
            vals = [app_id, n, now()] + [_enc(k, data.get(k)) for k in VERSION_COLS]
            cur = c.execute(f"INSERT INTO versions ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
            return cur.lastrowid

    def get_application(self, app_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        return _dec(row) if row else None

    def get_versions(self, app_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM versions WHERE application_id = ? ORDER BY version_no", (app_id,)).fetchall()
        return [_dec(r) for r in rows]

    def list_applications(self) -> list[dict]:
        sql = """
            SELECT a.id, a.created_at, a.company, a.job_title,
                   COUNT(v.id) AS versions, MAX(v.ats_after) AS best_ats,
                   COALESCE(SUM(v.cost_usd), 0) AS cost_usd,
                   MAX(CASE WHEN v.is_final THEN v.version_no END) AS final_version
            FROM applications a LEFT JOIN versions v ON v.application_id = a.id
            GROUP BY a.id ORDER BY a.id DESC"""
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql).fetchall()]

    def set_final(self, app_id: int, version_id: int) -> None:
        with self._conn() as c:
            c.execute("UPDATE versions SET is_final = (id = ?) WHERE application_id = ?", (version_id, app_id))

    def delete_application(self, app_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM applications WHERE id = ?", (app_id,))

    def log_usage(self, entries: list[dict], app_id=None, version_id=None, company=None) -> None:
        if not entries:
            return
        with self._conn() as c:
            c.executemany(
                "INSERT INTO usage_log (application_id, version_id, company, step, model, prompt_tokens,"
                " completion_tokens, cost_usd, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(app_id, version_id, company, e["step"], e["model"], e["prompt_tokens"],
                  e["completion_tokens"], e["cost_usd"], now()) for e in entries],
            )

    def usage_rows(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM usage_log ORDER BY id").fetchall()]
