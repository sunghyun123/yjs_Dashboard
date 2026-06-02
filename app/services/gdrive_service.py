import io
import json
import logging
import re
import threading
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
_PHOTO_ROOT_NAME = "공사별 사진 모음"


class GoogleDriveService:
    def __init__(self, shared_drive_id: str, sa_file: str = "", sa_json: str = ""):
        self._sa_file = sa_file
        self._sa_json = sa_json
        self._drive_id = shared_drive_id
        self._local = threading.local()  # 스레드마다 별도 service 인스턴스
        self._folder_cache: dict[str, str] = {}

    def _svc(self):
        if not hasattr(self._local, "service"):
            if self._sa_json:
                info = json.loads(self._sa_json)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=SCOPES
                )
            else:
                creds = service_account.Credentials.from_service_account_file(
                    self._sa_file, scopes=SCOPES
                )
            self._local.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._local.service

    def _find_folder(self, name: str, parent_id: str) -> Optional[str]:
        key = f"{parent_id}|{name}"
        if key in self._folder_cache:
            return self._folder_cache[key]
        escaped = name.replace("'", "\\'")
        q = (
            f"name='{escaped}' "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents "
            f"and trashed=false"
        )
        res = self._svc().files().list(
            q=q,
            spaces="drive",
            fields="files(id)",
            driveId=self._drive_id,
            corpora="drive",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])
        if files:
            fid = files[0]["id"]
            self._folder_cache[key] = fid
            return fid
        return None

    def _create_folder(self, name: str, parent_id: str) -> str:
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self._svc().files().create(
            body=meta, fields="id", supportsAllDrives=True
        ).execute()
        fid = folder["id"]
        self._folder_cache[f"{parent_id}|{name}"] = fid
        return fid

    def _find_or_create_folder(self, name: str, parent_id: str) -> str:
        return self._find_folder(name, parent_id) or self._create_folder(name, parent_id)

    @staticmethod
    def _safe_name(text: str, max_len: int = 80) -> str:
        text = re.sub(r'[\\/:*?"<>|]', "", text).strip()
        return text[:max_len]

    def upload_photo(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        work_code: str,
        task_name: str,
        date_str: str,
    ) -> str:
        """
        공사별 사진 모음 / {코드}_{공사명} / {날짜} / {파일} 구조로 업로드.
        업로드된 파일의 webViewLink 반환.
        """
        drive_root = self._drive_id

        photo_root_id = self._find_or_create_folder(_PHOTO_ROOT_NAME, drive_root)

        if work_code and task_name:
            constr_folder_name = self._safe_name(f"{work_code}_{task_name}")
        elif work_code:
            constr_folder_name = self._safe_name(work_code)
        elif task_name:
            constr_folder_name = self._safe_name(task_name)
        else:
            constr_folder_name = "미지정"
        constr_folder_id = self._find_or_create_folder(constr_folder_name, photo_root_id)

        date_folder_id = self._find_or_create_folder(date_str, constr_folder_id)

        safe_filename = self._safe_name(filename, 200)
        file_meta = {"name": safe_filename, "parents": [date_folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)
        uploaded = self._svc().files().create(
            body=file_meta,
            media_body=media,
            fields="id,webViewLink",
            supportsAllDrives=True,
        ).execute()

        logger.info(f"드라이브 업로드 완료: {constr_folder_name}/{date_str}/{safe_filename}")
        return uploaded.get("webViewLink", "")
