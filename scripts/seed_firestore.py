"""포트폴리오/데모용 시드 데이터를 Firestore `daily_metrics`에 생성한다.

혼합 전략: 과거 구간은 현실적인 시드 데이터로 채우고(`data_source="seed"`),
현재 시점부터는 운영 백업이 만드는 실데이터(`data_source="live"`)가 이어진다.

시드 데이터 특성(진짜처럼 보이게)
- 주간 계절성: 평일 ↑, 토/일 ↓
- 성장 추세: 기간에 걸쳐 사용량이 점진적으로 증가
- 노이즈: 날짜별 무작위 변동
- 내부 정합성: 로그인세션 ≥ DAU, 감사로그 = 일정 생성+수정+삭제(+α)
- 재현성: 날짜별 난수 시드를 고정 → 재실행해도 같은 값(멱등)

실행:
    python -m scripts.seed_firestore                       # 기본 구간(2026-03-01~어제)
    python -m scripts.seed_firestore --start 2026-04-01    # 시작일 지정
    python -m scripts.seed_firestore --dry-run             # 미리보기
"""
import argparse
import random
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from app.core.config import settings
from app.services.firestore_export_service import push_daily_metrics

DEFAULT_START = "2026-03-01"


def _weekend_factor(d: date) -> float:
    """평일=1.0, 토=0.45, 일=0.2. 가끔(5%) 공휴일성 저조일."""
    wd = d.weekday()  # 0=월 ... 6=일
    if wd == 5:
        return 0.45
    if wd == 6:
        return 0.2
    return 1.0


def _generate_metrics(d: date, progress: float) -> Dict[str, Any]:
    """하루치 현실적 운영지표를 생성한다. progress: 0(시작)~1(끝)."""
    random.seed(d.toordinal())  # 날짜별 고정 시드 → 재현 가능
    wf = _weekend_factor(d)
    if random.random() < 0.05:  # 가끔 비는 날
        wf *= 0.3

    def noisy(base: float, lo: float = 0.7, hi: float = 1.3) -> int:
        return max(0, round(base * wf * random.uniform(lo, hi)))

    # 활성 사용자(DAU): 기간에 걸쳐 3 → 13명으로 성장
    dau = noisy(3 + progress * 10, 0.8, 1.2)
    # 당일 등록된 공사일정 수: 4 → 20건으로 성장
    active_schedule = noisy(4 + progress * 16)
    # 신규 생성/수정/삭제(생성에 종속, 정합성 유지)
    created = noisy(active_schedule * 0.25, 0.5, 1.5)
    updated = max(0, round(created * random.uniform(0.3, 0.9)))
    deleted = max(0, round(created * random.uniform(0.0, 0.25)))
    # AI 채팅 사용(가장 빠르게 성장): 2 → 27건
    chat = noisy(2 + progress * 25, 0.6, 1.4)
    # 사진 업로드 / 관리자 요청
    photo = noisy(2, 0.0, 2.0)
    admin_req = 1 if random.random() < 0.15 * wf else 0
    # 감사로그 = 일정 변경 합계 + 소량
    audit = created + updated + deleted + random.randint(0, 2)
    # 로그인 세션 ≥ DAU
    login = dau + random.randint(0, 3)
    # 외출상태 스냅샷(전체 직원 수에 가까운 안정값)
    outing = random.randint(6, 10)

    return {
        "target_date": d.strftime("%Y-%m-%d"),
        "daily_active_user_count": dau,
        "active_schedule_count": active_schedule,
        "schedule_created_count": created,
        "schedule_update_count": updated,
        "schedule_delete_count": deleted,
        "chat_count": chat,
        "photo_upload_count": photo,
        "admin_request_count": admin_req,
        "audit_event_count": audit,
        "login_session_count": login,
        "outing_status_snapshot_count": outing,
    }


def _date_range(start: date, end: date) -> List[date]:
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Firestore 시드 데이터 생성")
    parser.add_argument("--start", default=DEFAULT_START, help="시작일(YYYY-MM-DD)")
    parser.add_argument("--end", default="", help="종료일(YYYY-MM-DD, 기본=어제)")
    parser.add_argument("--dry-run", action="store_true", help="저장 없이 미리보기")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = (datetime.strptime(args.end, "%Y-%m-%d").date()
           if args.end else date.today() - timedelta(days=1))
    if end < start:
        print("✗ 종료일이 시작일보다 빠릅니다.")
        return
    if not settings.firebase_enabled and not args.dry_run:
        print("✗ Firestore 비활성화 상태입니다. FIREBASE_CREDENTIALS_FILE을 확인하세요.")
        return

    dates = _date_range(start, end)
    total = len(dates)
    print(f"시드 구간: {start} ~ {end} ({total}일)\n")

    pushed = 0
    for i, d in enumerate(dates):
        progress = i / max(total - 1, 1)
        metrics = _generate_metrics(d, progress)
        if args.dry_run:
            if i % 7 == 0 or i == total - 1:  # 미리보기는 주 1회만 출력
                print(f"  · {metrics['target_date']} ({d.strftime('%a')}): "
                      f"dau={metrics['daily_active_user_count']}, "
                      f"sched={metrics['active_schedule_count']}, "
                      f"chat={metrics['chat_count']}")
            continue
        if push_daily_metrics(metrics, source="seed"):
            pushed += 1

    if args.dry_run:
        print(f"\n(dry-run) {total}일치 생성 예정")
    else:
        print(f"\n완료 - 시드 {pushed}/{total}일 저장")


if __name__ == "__main__":
    main()
