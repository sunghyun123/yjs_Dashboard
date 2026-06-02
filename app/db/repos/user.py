# app/db/repos/user.py
import secrets
from typing import Dict, Any, List, Optional

import bcrypt

from app.db.connection import get_conn


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class UserRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            row = conn.execute(
                "SELECT user_id, user_name, password_hash, register_code, role FROM users WHERE user_id=?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def ensure_oauth_user(self, user_id: str, user_name: str, role: str) -> None:
        u_id = (user_id or "").strip()
        u_name = (user_name or "").strip() or u_id
        r_db = "admin" if str(role or "").strip().lower() == "admin" else "worker"
        if not u_id:
            raise ValueError("user_id가 비어 있습니다.")
        random_pw = secrets.token_urlsafe(48)
        pw_hash = hash_password(random_pw)
        with get_conn(self._db_path) as conn:
            with conn:
                row = conn.execute("SELECT user_id FROM users WHERE user_id=?", (u_id,)).fetchone()
                if row:
                    conn.execute("UPDATE users SET user_name=?, role=? WHERE user_id=?", (u_name, r_db, u_id))
                else:
                    conn.execute(
                        "INSERT INTO users (user_id, user_name, password_hash, register_code, role) VALUES (?,?,?,?,?)",
                        (u_id, u_name, pw_hash, "", r_db),
                    )

    def upsert_login_access_request(self, kakao_id: str, note: str = "") -> Dict[str, Any]:
        k_id = str(kakao_id or "").strip()
        if not k_id:
            raise ValueError("kakao_id가 비어 있습니다.")
        default_id = f"kakao_{k_id}"
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO login_access_requests
                    (kakao_id, user_id, user_name, role, status, requested_at, note)
                    VALUES (?, ?, ?, 'worker', 'pending', datetime('now', 'localtime'), ?)
                    ON CONFLICT(kakao_id) DO UPDATE SET
                        status='pending', requested_at=datetime('now', 'localtime'), note=excluded.note
                    """,
                    (k_id, default_id, default_id, note),
                )
                row = conn.execute(
                    "SELECT id, kakao_id, user_id, user_name, role, status, requested_at, reviewed_at, reviewed_by, note FROM login_access_requests WHERE kakao_id=?",
                    (k_id,),
                ).fetchone()
                return dict(row) if row else {}

    def get_login_access_by_kakao_id(self, kakao_id: str) -> Optional[Dict[str, Any]]:
        k_id = str(kakao_id or "").strip()
        if not k_id:
            return None
        with get_conn(self._db_path) as conn:
            row = conn.execute(
                "SELECT id, kakao_id, user_id, user_name, role, status, requested_at, reviewed_at, reviewed_by, note FROM login_access_requests WHERE kakao_id=?",
                (k_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_login_access_requests(self, status: str = "pending") -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, kakao_id, user_id, user_name, role, status, requested_at, reviewed_at, reviewed_by, note FROM login_access_requests WHERE status=? ORDER BY requested_at DESC, id DESC",
                ((status or "pending").strip(),),
            ).fetchall()
            return [dict(r) for r in rows]

    def review_login_access_request(self, request_id: int, decision: str, reviewed_by: str, role: str = "worker", note: str = "") -> Dict[str, Any]:
        req_id = int(request_id)
        dec = (decision or "").strip().lower()
        rv_by = (reviewed_by or "").strip() or "admin"
        rv_role = "admin" if str(role or "").strip().lower() == "admin" else "worker"
        rv_note = str(note or "").strip()
        with get_conn(self._db_path) as conn:
            with conn:
                row = conn.execute(
                    "SELECT id, kakao_id, user_id, user_name, role, status, requested_at, reviewed_at, reviewed_by, note FROM login_access_requests WHERE id=?",
                    (req_id,),
                ).fetchone()
                if not row:
                    raise ValueError("요청을 찾을 수 없습니다.")
                current = dict(row)
                if current.get("status") != "pending":
                    raise ValueError("이미 처리된 요청입니다.")

                if dec == "approve":
                    next_uid = str(current.get("user_id") or "").strip() or f"kakao_{current['kakao_id']}"
                    next_uname = str(current.get("user_name") or "").strip() or next_uid
                    conn.execute(
                        "UPDATE login_access_requests SET status='approved', role=?, user_id=?, user_name=?, reviewed_at=datetime('now','localtime'), reviewed_by=?, note=? WHERE id=?",
                        (rv_role, next_uid, next_uname, rv_by, rv_note, req_id),
                    )
                elif dec == "reject":
                    conn.execute(
                        "UPDATE login_access_requests SET status='rejected', reviewed_at=datetime('now','localtime'), reviewed_by=?, note=? WHERE id=?",
                        (rv_by, rv_note, req_id),
                    )
                else:
                    raise ValueError("decision 값이 올바르지 않습니다.")

                reviewed = conn.execute(
                    "SELECT id, kakao_id, user_id, user_name, role, status, requested_at, reviewed_at, reviewed_by, note FROM login_access_requests WHERE id=?",
                    (req_id,),
                ).fetchone()
                return dict(reviewed) if reviewed else {}

    def create_session(self, session_id: str, user_id: str, device_name: str, expires_at: str) -> None:
        user = self.get_by_id(user_id)
        if not user:
            raise ValueError("사용자를 찾을 수 없습니다.")
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO sessions (session_id, user_id, role, device_name, expires_at) VALUES (?,?,?,?,?)",
                    (session_id, user_id, user["role"], device_name, expires_at),
                )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            row = conn.execute(
                "SELECT session_id, user_id, role, device_name, expires_at FROM sessions WHERE session_id=? AND datetime(expires_at) > datetime('now')",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, session_id: str) -> None:
        with get_conn(self._db_path) as conn:
            with conn:
                conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))

    def list_daily_sessions(self, target_date: str) -> List[Dict[str, Any]]:
        with get_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT session_id, user_id, role, device_name, expires_at, datetime(created_at,'localtime') AS created_at FROM sessions WHERE date(datetime(created_at,'localtime'))=? ORDER BY created_at DESC",
                (target_date,),
            ).fetchall()
            return [dict(r) for r in rows]
