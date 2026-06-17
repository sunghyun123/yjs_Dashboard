"""Firestore 연동: 일별 운영지표를 클라우드로 동기화한다.

포트폴리오용 데이터 파이프라인의 한 축.
SQLite(운영 DB) → 일별 집계(metrics) → Firestore(분석 스토어) → BI 시각화(Looker Studio/BigQuery).

설계 원칙
- 본 모듈은 항상 선택적이다. 서비스 계정 키가 없거나 firebase-admin이 없으면
  조용히 no-op 하고, Excel 백업 등 핵심 경로를 절대 막지 않는다.
- 컬렉션 `daily_metrics`의 문서 ID를 날짜(YYYY-MM-DD)로 두어 멱등(idempotent)하게
  덮어쓴다. 같은 날짜를 재실행해도 중복 행이 생기지 않는다. 이 컬렉션 자체가
  곧 일별 시계열 데이터셋이 된다.
"""
import logging
import threading
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 분석용 시계열 컬렉션 이름
DAILY_METRICS_COLLECTION = "daily_metrics"

# firebase_admin 앱은 프로세스당 한 번만 초기화한다.
_init_lock = threading.Lock()
_firestore_client = None
_init_failed = False


def _get_client():
    """Firestore 클라이언트를 지연 초기화해서 반환한다. 비활성/실패 시 None."""
    global _firestore_client, _init_failed

    if _firestore_client is not None:
        return _firestore_client
    if _init_failed or not settings.firebase_enabled:
        return None

    with _init_lock:
        if _firestore_client is not None:
            return _firestore_client
        if _init_failed:
            return None
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            if not firebase_admin._apps:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_FILE)
                firebase_admin.initialize_app(cred)
            _firestore_client = firestore.client()
            logger.info("Firestore 클라이언트 초기화 완료")
        except Exception as e:
            _init_failed = True
            logger.warning("Firestore 초기화 실패 — 동기화를 건너뜁니다: %s", e)
            return None
    return _firestore_client


def push_daily_metrics(metrics: Dict[str, Any], source: str = "live") -> Optional[str]:
    """일별 운영지표를 Firestore `daily_metrics/{date}` 문서에 멱등 저장한다.

    source: 데이터 출처 태그(data_source 필드로 저장). 데이터 계보 추적용.
        - "live": 운영 중 자동 백업이 생성한 실데이터(기본값)
        - "seed": 데모/포트폴리오용 시드 데이터
        - "backfill": 과거 백업 파일에서 복원한 실데이터

    반환: 저장한 문서 경로(성공) 또는 None(비활성/실패).
    예외는 던지지 않는다 — 호출부(백업 경로)를 막지 않기 위함.
    """
    client = _get_client()
    if client is None:
        return None

    target_date = str(metrics.get("target_date", "") or "").strip()
    if not target_date:
        logger.warning("Firestore 동기화 생략: metrics에 target_date 없음")
        return None

    try:
        from firebase_admin import firestore

        # int 값만 추려 깔끔한 분석용 도큐먼트를 구성한다(target_date는 별도 보존).
        doc: Dict[str, Any] = {
            k: int(v) for k, v in metrics.items()
            if k != "target_date" and isinstance(v, (int, bool))
        }
        doc["date"] = target_date
        doc["data_source"] = source
        doc["synced_at"] = firestore.SERVER_TIMESTAMP

        ref = client.collection(DAILY_METRICS_COLLECTION).document(target_date)
        ref.set(doc, merge=True)
        path = f"{DAILY_METRICS_COLLECTION}/{target_date}"
        logger.info("Firestore 동기화 완료: %s", path)
        return path
    except Exception as e:
        logger.warning("Firestore 동기화 실패(%s): %s", target_date, e)
        return None
