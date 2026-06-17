"""기존 백업 xlsx의 운영지표를 Firestore로 일괄 백필(backfill)한다.

용도: Firestore 연동 이전에 생성된 과거 백업 파일들의 일별 운영지표를
`daily_metrics` 컬렉션으로 밀어넣어 시계열 데이터셋을 채운다.
문서 ID가 날짜라서 멱등하다 — 여러 번 실행해도 안전하다.

실행:
    python -m scripts.backfill_firestore           # uploads/ + 루트의 모든 백업
    python -m scripts.backfill_firestore --dry-run # 저장 없이 미리보기
"""
import argparse
import glob
import os
import re
from typing import Any, Dict, List

import pandas as pd

from app.core.config import settings
from app.services.firestore_export_service import push_daily_metrics

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _collect_backup_files() -> List[str]:
    """백업 xlsx 경로를 날짜순으로 모은다(uploads/ + 프로젝트 루트)."""
    files = glob.glob("uploads/*_백업데이터.xlsx") + glob.glob("*_백업데이터.xlsx")
    # 중복 파일명 제거 후 파일명의 날짜 기준 정렬
    unique = {os.path.basename(f): f for f in files}
    return sorted(unique.values(), key=lambda p: os.path.basename(p))


def _read_metrics(path: str) -> Dict[str, Any]:
    """xlsx의 운영지표 시트를 {metric: value} dict로 읽고 target_date를 보강한다."""
    date_match = DATE_RE.search(os.path.basename(path))
    if not date_match:
        return {}
    target_date = date_match.group(1)

    xl = pd.ExcelFile(path)
    if "운영지표" not in xl.sheet_names:
        return {}

    df = xl.parse("운영지표")
    metrics: Dict[str, Any] = {"target_date": target_date}
    for metric, value in zip(df["metric"], df["value"]):
        key = str(metric).strip()
        if not key or key == "target_date":
            continue
        # numpy int64 등을 파이썬 int로 강제 변환(Firestore 동기화 필터 통과용)
        try:
            metrics[key] = int(value)
        except (TypeError, ValueError):
            continue
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="기존 백업 xlsx → Firestore 백필")
    parser.add_argument("--dry-run", action="store_true", help="저장 없이 미리보기")
    args = parser.parse_args()

    if not settings.firebase_enabled and not args.dry_run:
        print("✗ Firestore 비활성화 상태입니다. FIREBASE_CREDENTIALS_FILE을 확인하세요.")
        return

    files = _collect_backup_files()
    print(f"백업 파일 {len(files)}개 발견\n")

    pushed, skipped = 0, 0
    for path in files:
        metrics = _read_metrics(path)
        date = metrics.get("target_date", "?")
        if not metrics or len(metrics) <= 1:
            print(f"  - {os.path.basename(path)}: 운영지표 없음 → 건너뜀")
            skipped += 1
            continue

        dau = metrics.get("daily_active_user_count", 0)
        sched = metrics.get("active_schedule_count", 0)
        if args.dry_run:
            print(f"  · {date}: dau={dau}, active_schedule={sched}, 지표 {len(metrics) - 1}개 (dry-run)")
            continue

        result = push_daily_metrics(metrics, source="backfill")
        if result:
            print(f"  ✓ {date}: dau={dau}, active_schedule={sched} → {result}")
            pushed += 1
        else:
            print(f"  ✗ {date}: 동기화 실패")
            skipped += 1

    print(f"\n완료 - 저장 {pushed}건, 건너뜀 {skipped}건")


if __name__ == "__main__":
    main()
