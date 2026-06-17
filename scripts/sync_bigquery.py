"""Firestore `daily_metrics` → BigQuery `analytics.daily_metrics` 동기화.

포트폴리오 데이터 파이프라인의 마지막 적재(load) 단계.
Firestore(분석 스토어)에 쌓인 일별 운영지표를 BigQuery 테이블로 전량 적재하면,
Looker Studio가 BigQuery 네이티브 커넥터로 바로 시각화할 수 있다.

설계
- 전량 새로고침(WRITE_TRUNCATE): 데이터가 작고(수백 행) 멱등성이 단순해 매번 통째로 덮어쓴다.
- 명시적 스키마: date를 DATE 타입으로 지정해 Looker Studio가 시간 차원으로 인식하게 한다.
- 위치(LOCATION)는 Firestore 리전과 맞춘 asia-northeast3(서울).

실행:
    python -m scripts.sync_bigquery            # Firestore 전량 → BigQuery 적재
    python -m scripts.sync_bigquery --dry-run  # 적재 없이 행 수만 미리보기
"""
import argparse
from typing import Any, Dict, List

from app.core.config import settings
from app.services.firestore_export_service import _get_client, DAILY_METRICS_COLLECTION

DATASET = "analytics"
TABLE = "daily_metrics"
LOCATION = "asia-northeast3"  # Firestore(서울) 리전과 일치

# 적재할 정수형 지표 컬럼(INT64)
METRIC_COLS = [
    "daily_active_user_count",
    "active_schedule_count",
    "schedule_created_count",
    "schedule_update_count",
    "schedule_delete_count",
    "chat_count",
    "photo_upload_count",
    "admin_request_count",
    "audit_event_count",
    "login_session_count",
    "outing_status_snapshot_count",
]


def _read_firestore_rows() -> List[Dict[str, Any]]:
    """Firestore daily_metrics 전체를 BigQuery 적재용 행으로 변환."""
    client = _get_client()
    if client is None:
        return []
    rows: List[Dict[str, Any]] = []
    for doc in client.collection(DAILY_METRICS_COLLECTION).order_by("date").stream():
        d = doc.to_dict()
        date = str(d.get("date", "") or "").strip()
        if not date:
            continue
        synced = d.get("synced_at")
        row: Dict[str, Any] = {
            "date": date,
            "data_source": d.get("data_source", "unknown"),
            # DatetimeWithNanoseconds → ISO 문자열(BQ TIMESTAMP 파싱용)
            "synced_at": synced.isoformat() if synced is not None else None,
        }
        for col in METRIC_COLS:
            row[col] = int(d.get(col, 0) or 0)
        rows.append(row)
    return rows


def _build_schema():
    from google.cloud import bigquery
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("data_source", "STRING"),
        bigquery.SchemaField("synced_at", "TIMESTAMP"),
    ]
    schema += [bigquery.SchemaField(col, "INT64") for col in METRIC_COLS]
    return schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Firestore → BigQuery 동기화")
    parser.add_argument("--dry-run", action="store_true", help="적재 없이 미리보기")
    args = parser.parse_args()

    if not settings.firebase_enabled:
        print("✗ Firestore 비활성화 상태입니다. FIREBASE_CREDENTIALS_FILE을 확인하세요.")
        return

    rows = _read_firestore_rows()
    print(f"Firestore에서 {len(rows)}행 읽음")
    if not rows:
        print("적재할 데이터가 없습니다.")
        return

    from collections import Counter
    print("data_source 분포:", dict(Counter(r["data_source"] for r in rows)))
    print(f"기간: {rows[0]['date']} ~ {rows[-1]['date']}")

    if args.dry_run:
        print("\n(dry-run) BigQuery 적재 생략")
        return

    from google.cloud import bigquery

    client = bigquery.Client.from_service_account_json(
        settings.FIREBASE_CREDENTIALS_FILE
    )
    dataset_id = f"{client.project}.{DATASET}"
    table_id = f"{dataset_id}.{TABLE}"

    # 데이터셋 보장(없으면 생성)
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = LOCATION
    client.create_dataset(dataset, exists_ok=True)

    job_config = bigquery.LoadJobConfig(
        schema=_build_schema(),
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_json(rows, table_id, job_config=job_config, location=LOCATION)
    job.result()  # 완료 대기

    table = client.get_table(table_id)
    print(f"\n완료 - {table_id}에 {table.num_rows}행 적재")
    print(f"콘솔: https://console.cloud.google.com/bigquery?project={client.project}")


if __name__ == "__main__":
    main()
