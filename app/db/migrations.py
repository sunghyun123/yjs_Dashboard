# app/db/migrations.py
from app.db.connection import get_conn


def run_migrations(db_path: str) -> None:
    """앱 시작 시 한 번만 호출. CREATE TABLE IF NOT EXISTS + ALTER TABLE 마이그레이션."""
    with get_conn(db_path) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS field_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    location TEXT,
                    task TEXT,
                    person TEXT,
                    details TEXT,
                    tags TEXT,
                    work_code TEXT,
                    shift_type TEXT,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cols = {row[1] for row in conn.execute("PRAGMA table_info(field_schedules)").fetchall()}
            _add_col_if_missing = lambda col, defn: conn.execute(
                f"ALTER TABLE field_schedules ADD COLUMN {col} {defn}"
            ) if col not in cols else None

            _add_col_if_missing("details", "TEXT")
            _add_col_if_missing("tags", "TEXT")
            _add_col_if_missing("work_code", "TEXT")
            _add_col_if_missing("shift_type", "TEXT")
            _add_col_if_missing("deleted_at", "TEXT")
            _add_col_if_missing("deleted_by", "TEXT")
            _add_col_if_missing("delete_reason", "TEXT")
            _add_col_if_missing("last_actor_user", "TEXT")
            _add_col_if_missing("last_actor_device", "TEXT")
            _add_col_if_missing("last_actor_at", "TEXT")
            _add_col_if_missing("display_order", "INTEGER DEFAULT 0")
            _add_col_if_missing("source_kind", "TEXT DEFAULT 'manual'")
            _add_col_if_missing("source_photo_upload_id", "INTEGER")
            _add_col_if_missing("photo_plan_acknowledged", "INTEGER NOT NULL DEFAULT 0")
            _add_col_if_missing("erp_data", "TEXT")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT,
                    password_hash TEXT NOT NULL,
                    register_code TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'worker',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "user_name" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN user_name TEXT")
            if "password_plain" in user_cols:
                conn.execute("UPDATE users SET password_plain = NULL WHERE password_plain IS NOT NULL AND password_plain != ''")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    device_name TEXT,
                    expires_at TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS login_access_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kakao_id TEXT NOT NULL UNIQUE,
                    user_id TEXT,
                    user_name TEXT,
                    role TEXT NOT NULL DEFAULT 'worker',
                    status TEXT NOT NULL DEFAULT 'pending',
                    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    note TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_type TEXT NOT NULL,
                    source_category TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    summary TEXT,
                    payload_json TEXT,
                    requested_by TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS photo_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    uploaded_by TEXT,
                    uploaded_device TEXT,
                    related_date TEXT,
                    file_size INTEGER DEFAULT 0,
                    file_sha256 TEXT DEFAULT '',
                    linked_schedule_id INTEGER,
                    note TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            photo_cols = {row[1] for row in conn.execute("PRAGMA table_info(photo_uploads)").fetchall()}
            if "file_size" not in photo_cols:
                conn.execute("ALTER TABLE photo_uploads ADD COLUMN file_size INTEGER DEFAULT 0")
            if "file_sha256" not in photo_cols:
                conn.execute("ALTER TABLE photo_uploads ADD COLUMN file_sha256 TEXT DEFAULT ''")
            if "linked_schedule_id" not in photo_cols:
                conn.execute("ALTER TABLE photo_uploads ADD COLUMN linked_schedule_id INTEGER")
            if "note" not in photo_cols:
                conn.execute("ALTER TABLE photo_uploads ADD COLUMN note TEXT DEFAULT ''")

            conn.execute("DROP TABLE IF EXISTS memo_items")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS worker_status (
                    user_name TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT '사무실',
                    location TEXT,
                    until_time TEXT,
                    note TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_actor_user TEXT,
                    last_actor_device TEXT,
                    last_actor_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS export_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    output_path TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS field_staff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    sort_order INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS outing_staff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    sort_order INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS frequent_sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER,
                    action TEXT NOT NULL,
                    before_json TEXT,
                    after_json TEXT,
                    reason TEXT,
                    actor_user TEXT,
                    actor_device TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    input_category TEXT,
                    intent TEXT,
                    message_text TEXT,
                    response_status TEXT NOT NULL DEFAULT 'success',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
