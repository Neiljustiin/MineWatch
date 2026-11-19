"""SQLite persistence for analyst work: decisions, assignments, audit trail.

Kept deliberately small (sqlite3 stdlib, no ORM). The DB lives in data/runtime/ and is
created on first start. Nothing here sends anything anywhere: "dispatch" is recorded as
a MOCK because alerting to DLHK/Polda is roadmap-only (see context.md).
"""
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import bcrypt

_lock = threading.Lock()
SESSION_TTL_HOURS = 12


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with _lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ref TEXT NOT NULL,
                    dispatch TEXT NOT NULL,          -- 'mock_alert' | 'closed'
                    recalled_at TEXT
                );
                CREATE TABLE IF NOT EXISTS assignments (
                    case_id TEXT PRIMARY KEY,
                    assignee TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    actor TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    at TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS ix_dec_case ON decisions(case_id);
                CREATE INDEX IF NOT EXISTS ix_audit_case ON audit(case_id);
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'Analyst',
                    last_login TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(username);
                CREATE TABLE IF NOT EXISTS admin_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT ''
                );
                """
            )
            # users.role / users.last_login: added after the table already existed in
            # earlier deployments -- ALTER TABLE ADD COLUMN is a no-op-safe upgrade path.
            cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(users)")}
            if "role" not in cols:
                self.conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'Analyst'")
            if "last_login" not in cols:
                self.conn.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
            self.conn.commit()

    # --------------------------------------------------------------- auth ----
    def get_user(self, username):
        r = self.conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(r) if r else None

    def seed_user(self, username, password, role="Analyst"):
        """Create the account only if it doesn't already exist — safe to call on every boot,
        and safe when two processes share the same DB file and boot at the same time."""
        if self.get_user(username):
            return
        h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with _lock:
            self.conn.execute("INSERT OR IGNORE INTO users(username, password_hash, created_at, role) VALUES (?,?,?,?)",
                              (username, h, now_iso(), role))
            self.conn.commit()

    def check_password(self, username, password):
        u = self.get_user(username)
        if not u:
            return False
        return bcrypt.checkpw(password.encode(), u["password_hash"].encode())

    def role_of(self, username):
        u = self.get_user(username)
        return u["role"] if u else None

    def touch_login(self, username):
        with _lock:
            self.conn.execute("UPDATE users SET last_login=? WHERE username=?", (now_iso(), username))
            self.conn.commit()

    # ------------------------------------------------------------ admin ----
    def list_users(self):
        rows = self.conn.execute("SELECT username, role, created_at, last_login FROM users ORDER BY created_at").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            dec = self.conn.execute("SELECT COUNT(*) AS n FROM decisions WHERE actor=?", (r["username"],)).fetchone()["n"]
            aud1 = self.conn.execute("SELECT COUNT(*) AS n FROM audit WHERE actor=?", (r["username"],)).fetchone()["n"]
            aud2 = self.conn.execute("SELECT COUNT(*) AS n FROM admin_log WHERE actor=?", (r["username"],)).fetchone()["n"]
            d["decisions_signed"] = dec
            d["audit_entries"] = aud1 + aud2
            out.append(d)
        return out

    def count_admins(self):
        return self.conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='Admin'").fetchone()["n"]

    def create_user(self, username, password, role):
        if self.get_user(username):
            raise ValueError("username already exists")
        h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with _lock:
            self.conn.execute("INSERT INTO users(username, password_hash, created_at, role) VALUES (?,?,?,?)",
                              (username, h, now_iso(), role))
            self.conn.commit()

    def set_password(self, username, password):
        h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with _lock:
            self.conn.execute("UPDATE users SET password_hash=? WHERE username=?", (h, username))
            self.conn.commit()

    def delete_user(self, username):
        with _lock:
            self.conn.execute("DELETE FROM users WHERE username=?", (username,))
            self.conn.execute("DELETE FROM sessions WHERE username=?", (username,))
            self.conn.commit()

    def admin_log_add(self, actor, action, detail=""):
        with _lock:
            self.conn.execute("INSERT INTO admin_log(at, actor, action, detail) VALUES (?,?,?,?)",
                              (now_iso(), actor, action, detail))
            self.conn.commit()

    def admin_log_list(self, since=None, q=None, limit=500):
        sql = "SELECT * FROM admin_log"
        args = []
        if since:
            sql += " WHERE at >= ?"
            args.append(since)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in self.conn.execute(sql, args).fetchall()]
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in (r["actor"] + " " + r["action"] + " " + r["detail"]).lower()]
        return rows

    def admin_log_count(self):
        return self.conn.execute("SELECT COUNT(*) AS n FROM admin_log").fetchone()["n"]

    def count_active_sessions(self):
        return self.conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE expires_at > ?", (now_iso(),)).fetchone()["n"]

    def create_session(self, username):
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat(timespec="seconds")
        with _lock:
            self.conn.execute("INSERT INTO sessions(token, username, created_at, expires_at) VALUES (?,?,?,?)",
                              (token, username, now_iso(), expires))
            self.conn.commit()
        return token

    def session_user(self, token):
        if not token:
            return None
        r = self.conn.execute("SELECT username, expires_at FROM sessions WHERE token=?", (token,)).fetchone()
        if not r:
            return None
        if datetime.fromisoformat(r["expires_at"]) < datetime.now(timezone.utc):
            self.delete_session(token)
            return None
        return r["username"]

    def delete_session(self, token):
        with _lock:
            self.conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            self.conn.commit()

    # ------------------------------------------------------------- reads ----
    def active_decision(self, case_id):
        r = self.conn.execute(
            "SELECT * FROM decisions WHERE case_id=? AND recalled_at IS NULL ORDER BY id DESC LIMIT 1",
            (case_id,)).fetchone()
        return dict(r) if r else None

    def all_active_decisions(self):
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE recalled_at IS NULL ORDER BY id").fetchall()
        return {r["case_id"]: dict(r) for r in rows}

    def assignment(self, case_id):
        r = self.conn.execute("SELECT * FROM assignments WHERE case_id=?", (case_id,)).fetchone()
        return dict(r) if r else None

    def all_assignments(self):
        return {r["case_id"]: dict(r) for r in self.conn.execute("SELECT * FROM assignments").fetchall()}

    def audit(self, case_id, limit=50):
        rows = self.conn.execute(
            "SELECT * FROM audit WHERE case_id=? ORDER BY id DESC LIMIT ?", (case_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def viewers(self, case_id):
        r = self.conn.execute(
            "SELECT COUNT(DISTINCT actor) AS n FROM audit WHERE case_id=? AND event='viewed'", (case_id,)).fetchone()
        return r["n"]

    # ------------------------------------------------------------ writes ----
    def log(self, case_id, event, actor, detail=""):
        with _lock:
            self.conn.execute("INSERT INTO audit(case_id, event, actor, at, detail) VALUES (?,?,?,?,?)",
                              (case_id, event, actor, now_iso(), detail))
            self.conn.commit()

    def log_view(self, case_id, actor):
        # one 'viewed' row per actor per case per hour is enough for an audit trail
        r = self.conn.execute(
            "SELECT at FROM audit WHERE case_id=? AND actor=? AND event='viewed' ORDER BY id DESC LIMIT 1",
            (case_id, actor)).fetchone()
        if r:
            last = datetime.fromisoformat(r["at"])
            if (datetime.now(timezone.utc) - last).total_seconds() < 3600:
                return
        self.log(case_id, "viewed", actor)

    def add_decision(self, case_id, decision, notes, actor, ref, dispatch):
        with _lock:
            cur = self.conn.execute(
                "INSERT INTO decisions(case_id, decision, notes, actor, created_at, ref, dispatch) VALUES (?,?,?,?,?,?,?)",
                (case_id, decision, notes, actor, now_iso(), ref, dispatch))
            self.conn.commit()
            rid = cur.lastrowid
        return dict(self.conn.execute("SELECT * FROM decisions WHERE id=?", (rid,)).fetchone())

    def recall(self, decision_id):
        with _lock:
            self.conn.execute("UPDATE decisions SET recalled_at=? WHERE id=?", (now_iso(), decision_id))
            self.conn.commit()

    def next_ref_seq(self):
        r = self.conn.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()
        return r["n"] + 1

    def set_assignment(self, case_id, assignee, actor):
        with _lock:
            self.conn.execute(
                "INSERT INTO assignments(case_id, assignee, updated_at, actor) VALUES (?,?,?,?) "
                "ON CONFLICT(case_id) DO UPDATE SET assignee=excluded.assignee, updated_at=excluded.updated_at, actor=excluded.actor",
                (case_id, assignee, now_iso(), actor))
            self.conn.commit()
