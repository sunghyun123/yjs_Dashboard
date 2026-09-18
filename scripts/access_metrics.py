#!/usr/bin/env python3
"""액세스 로그 집계 — 가용성·응답속도·사용량 운영지표.

읽는 것: `main.py` 의 AccessLogMiddleware 가 찍는 한 줄 로그.
    INFO [access] 1.235.19.128 user=admin(admin) GET /api/schedules/today 200 3.8ms

실행 (stdin 으로 받는다 — 서버에 이 파일을 배포할 필요가 없다):

  # 로컬에서 원격 서버 로그를 바로 집계
  ssh root@115.68.228.200 \
    'journalctl -u yjs-dashboard -o short-iso --since "2026-09-01" --no-pager' \
    | python scripts/access_metrics.py

  # 서버에서 직접
  journalctl -u yjs-dashboard -o short-iso --since "2026-09-01" --no-pager \
    | python3 access_metrics.py --since 2026-09-03 --until 2026-09-18

  # 일별 표를 CSV 로
  ... | python3 access_metrics.py --csv > access_daily.csv

⚠️ journalctl 은 반드시 `-o short-iso` 로 넘긴다. `-o cat` 은 시각을 떼버려서
   일별 집계가 통째로 불가능해지는데, 그걸 조용히 0으로 처리하면 안 되므로
   이 스크립트는 시각이 없으면 집계를 멈추고 에러로 알린다.

⚠️ 이 로그는 2026-09-03 배포분부터 존재한다. 그 앞 기간을 지정해도 에러가 아니라
   "그 기간 줄이 없음"으로 조용히 끝나므로, 리포트 맨 위의 '데이터 가용 시점'을
   먼저 읽고 보고서에 기간을 못 박는다. (scripts/q3_report.sql 의 [1]번과 같은 처방)
"""
import argparse
import collections
import csv
import re
import sys

# 윈도우 콘솔은 기본이 cp949라 em-dash 같은 글자 하나에 print 가 UnicodeEncodeError 로 죽는다.
# 집계는 다 끝났는데 출력 한 글자 때문에 리포트 전체가 실패로 둔갑하면 안 되므로,
# 못 찍는 글자는 대체 문자로 흘려보낸다. (출력 실패가 본 작업 실패가 되지 않게)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

# 로그 한 줄에서 [access] 뒤의 본문만 본다. 앞쪽(시각·호스트·pid)은 journalctl 포맷이라 건드리지 않는다.
ACCESS_MARK = "[access]"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T")

# 사용자 식별이 안 되는 라벨. 활성 사용자 집계에서 뺀다.
NON_USERS = {"anon", "invalid-session"}


def parse_line(line):
    """한 줄 → dict. 형식이 안 맞으면 None (호출부가 실패 건수를 센다)."""
    tokens = line.split()
    try:
        mark = tokens.index(ACCESS_MARK)
    except ValueError:
        return None
    rest = tokens[mark + 1:]
    # ip / user= / METHOD / path... / status / ms  — 경로에 공백이 섞여도 되게 양끝에서 자른다
    if len(rest) < 6:
        return None
    if not ISO_DATE.match(tokens[0]):
        return "NO_TIMESTAMP"
    try:
        status = int(rest[-2])
        duration = float(rest[-1].rstrip("ms"))
    except ValueError:
        return None
    user = rest[1][5:] if rest[1].startswith("user=") else ""
    return {
        "date": tokens[0][:10],
        "hour": tokens[0][11:13],
        "ip": rest[0],
        "user": user.split("(")[0],
        "method": rest[2],
        "path": " ".join(rest[3:-2]).split("?")[0],  # 쿼리스트링은 떼야 경로별 집계가 뭉친다
        "status": status,
        "ms": duration,
    }


def percentile(sorted_values, q):
    if not sorted_values:
        return 0.0
    return sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * q))]


def main():
    ap = argparse.ArgumentParser(description="액세스 로그 운영지표 집계")
    ap.add_argument("--since", default="", help="YYYY-MM-DD (이 날짜 포함, 미지정 시 전체)")
    ap.add_argument("--until", default="", help="YYYY-MM-DD (이 날짜 포함, 미지정 시 전체)")
    ap.add_argument("--csv", action="store_true", help="일별 표를 CSV 로 출력")
    ap.add_argument("--top", type=int, default=8, help="경로 목록을 몇 개까지 보여줄지")
    args = ap.parse_args()

    total = read = skipped = no_timestamp = 0
    durations = []
    family = collections.Counter()
    day_requests = collections.Counter()
    day_users = collections.defaultdict(set)
    day_errors = collections.Counter()
    path_times = collections.defaultdict(list)
    # 4xx 를 한 덩어리로 세면 외부 스캐너가 우리 오류율로 둔갑한다.
    # 경로 이름으로 "우리 것/봇" 을 가르려 했다가 틀렸다(스캐너가 /api/.env 도 두드린다).
    # 그래서 추측이 안 들어가는 기준, 즉 **상태코드의 의미**로 가른다:
    #   404 = 그런 경로가 없다   -> 우리 화면은 없는 경로를 부르지 않으므로 사실상 외부 탐색
    #   401/403 = 신원이 없거나 권한이 없다 -> 로그인 전 정상 흐름일 수 있다
    #   그 외 4xx(400/405/422...) = 요청은 닿았는데 우리가 거절했다 -> 진짜 앱 오류 후보
    server_5xx = collections.Counter()
    not_found_404 = collections.Counter()
    auth_4xx = collections.Counter()
    app_4xx = collections.Counter()

    for line in sys.stdin:
        read += 1
        row = parse_line(line)
        if row == "NO_TIMESTAMP":
            no_timestamp += 1
            continue
        if row is None:
            if ACCESS_MARK in line:
                skipped += 1  # access 줄인데 못 읽은 것만 실패로 센다(무관한 줄은 실패가 아니다)
            continue
        if args.since and row["date"] < args.since:
            continue
        if args.until and row["date"] > args.until:
            continue

        total += 1
        durations.append(row["ms"])
        family[row["status"] // 100] += 1
        day_requests[row["date"]] += 1
        path_times[row["path"]].append(row["ms"])
        if row["user"] and row["user"] not in NON_USERS:
            day_users[row["date"]].add(row["user"])
        if row["status"] >= 500:
            server_5xx[(row["status"], row["path"])] += 1
            day_errors[row["date"]] += 1
        elif row["status"] == 404:
            not_found_404[(row["status"], row["path"])] += 1
        elif row["status"] in (401, 403):
            auth_4xx[(row["status"], row["path"])] += 1
        elif row["status"] >= 400:
            app_4xx[(row["status"], row["path"])] += 1

    if no_timestamp:
        sys.exit(
            f"오류: 시각 없는 줄이 {no_timestamp}건입니다. journalctl 에 '-o short-iso' 를 붙여 주세요.\n"
            "      (시각이 없으면 일별 집계가 불가능한데, 0으로 채우면 조용히 틀린 표가 나옵니다.)"
        )
    if total == 0:
        sys.exit(f"오류: 집계할 access 줄이 0건입니다 (입력 {read}줄). 기간 또는 journalctl 범위를 확인하세요.")

    durations.sort()
    if args.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["date", "requests", "unique_users", "server_errors_5xx"])
        for day in sorted(day_requests):
            writer.writerow([day, day_requests[day], len(day_users.get(day, ())), day_errors[day]])
        return

    days = sorted(day_requests)

    print("=" * 68)
    print("액세스 로그 운영지표")
    print("=" * 68)
    # ★ 항상 맨 위에 찍는다 — 이 숫자가 '언제부터'인지를 보고서에 못 박기 위한 것
    print(f"데이터 가용 시점 : {days[0]} ~ {days[-1]}  ({len(days)}일)")
    print(f"총 요청          : {total:,}건")
    if skipped:
        print(f"[주의] 형식이 안 맞아 못 읽은 access 줄 : {skipped}건 "
              f"({skipped / (total + skipped) * 100:.1f}%) - 아래 숫자는 그만큼 모자랍니다")

    print()
    print("[가용성]  * 보고에 쓸 오류율은 5xx 와 '앱 4xx' 뿐이다")
    print(f"  정상(2xx/3xx)        : {family[2] + family[3]:,}")
    print(f"  서버 오류(5xx)       : {family[5]:,}  ({family[5] / total * 100:.3f}%)"
          f"   정상 응답률 {100 - family[5] / total * 100:.2f}%")
    print(f"  앱 4xx(400/405/422..): {sum(app_4xx.values()):,}   <- 요청은 닿았는데 거절함. 진짜 오류 후보")
    print(f"  인증 4xx(401/403)    : {sum(auth_4xx.values()):,}   <- 로그인 전 정상 흐름일 수 있음")
    print(f"  없는 경로(404)       : {sum(not_found_404.values()):,}   <- 대부분 외부 탐색. 오류율에 넣지 말 것")

    print()
    print("[응답시간 ms]")
    print(f"  p50 {percentile(durations, 0.50):.1f}   p95 {percentile(durations, 0.95):.1f}"
          f"   p99 {percentile(durations, 0.99):.1f}   최대 {durations[-1]:.1f}")

    print()
    print("[일별]  날짜        요청     로그인사용자  5xx")
    for day in days:
        print(f"        {day}  {day_requests[day]:>7,}  {len(day_users.get(day, ())):>10}"
              f"  {day_errors[day]:>4}")

    print()
    print(f"[느린 경로 top{args.top}]  평균ms   호출수  경로   (호출 5회 미만 제외 - 평균이 흔들림)")
    frequent = {p: t for p, t in path_times.items() if len(t) >= 5}
    for path, times in sorted(frequent.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))[:args.top]:
        print(f"        {sum(times) / len(times):>8.1f}  {len(times):>7,}  {path}")

    # 분류가 맞는지 사람이 눈으로 확인할 수 있게 실제 경로를 찍는다.
    # (오늘 ERP 지표가 틀렸던 이유가 '정의를 검산하지 않은 것'이었다)
    for title, counter in (("서버 오류 5xx - 진짜 장애", server_5xx),
                           ("앱 4xx - 여기를 봐야 한다", app_4xx),
                           ("인증 4xx (401/403)", auth_4xx),
                           ("없는 경로 404 - 분류가 맞는지 직접 확인할 것", not_found_404)):
        print()
        print(f"[{title}]")
        if not counter:
            print("        (없음)")
        for (status, path), count in counter.most_common(args.top):
            print(f"        {status}  {count:>6,}  {path}")


if __name__ == "__main__":
    main()
