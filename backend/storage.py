import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
GOOGLE_TOKEN_DIR = DATA_DIR / "google_tokens"
DB_PATH = DATA_DIR / "lifeos.sqlite3"

for path in (DATA_DIR, UPLOAD_DIR, GOOGLE_TOKEN_DIR):
    path.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tool_connections (
                user_id INTEGER PRIMARY KEY,
                gmail_enabled INTEGER NOT NULL DEFAULT 0,
                calendar_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                pages INTEGER NOT NULL DEFAULT 0,
                chunks INTEGER NOT NULL DEFAULT 0,
                uploaded_at TEXT NOT NULL,
                UNIQUE(user_id, filename),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def create_user(email: str, password: str):
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email.strip().lower(), hash_password(password), utc_now()),
        )
        user_id = cursor.lastrowid
        db.execute(
            "INSERT OR IGNORE INTO tool_connections (user_id, updated_at) VALUES (?, ?)",
            (user_id, utc_now()),
        )
        return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_email(email: str):
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()


def get_user_by_id(user_id: int):
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    with get_db() as db:
        db.execute(
            "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, expires_at, utc_now()),
        )
    return token


def delete_session(token: str):
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_user_for_token(token: str):
    with get_db() as db:
        row = db.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, utc_now()),
        ).fetchone()
    return row


def get_connections(user_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM tool_connections WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            db.execute("INSERT INTO tool_connections (user_id, updated_at) VALUES (?, ?)", (user_id, utc_now()))
            row = db.execute("SELECT * FROM tool_connections WHERE user_id = ?", (user_id,)).fetchone()
        return row


def set_connection(user_id: int, gmail: bool | None = None, calendar: bool | None = None):
    current = get_connections(user_id)
    gmail_enabled = current["gmail_enabled"] if gmail is None else int(gmail)
    calendar_enabled = current["calendar_enabled"] if calendar is None else int(calendar)
    with get_db() as db:
        db.execute(
            """
            INSERT INTO tool_connections (user_id, gmail_enabled, calendar_enabled, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                gmail_enabled = excluded.gmail_enabled,
                calendar_enabled = excluded.calendar_enabled,
                updated_at = excluded.updated_at
            """,
            (user_id, gmail_enabled, calendar_enabled, utc_now()),
        )


def google_token_path(user_id: int) -> Path:
    return GOOGLE_TOKEN_DIR / f"user_{user_id}.json"
