-- ============================================================================
--  3분기(2026-07-01 ~ 2026-09-30) 운영지표 보고용 쿼리 모음
--  대상 DB: 운영 서버의 schedule.db  (개발 PC의 schedule.db는 테스트 데이터다)
--
--  실행:
--    sqlite3 -header -csv schedule.db < scripts/q3_report.sql > q3_report.csv
--    (쿼리별로 따로 뽑으려면 필요한 블록만 잘라서 실행)
--
--  기간 변경: 각 쿼리 첫 줄의 p(s,e) 날짜 두 개만 고치면 된다.
--
--  ⚠️ 읽기 전 반드시 알아야 할 것 두 가지
--  1) usage_events 테이블은 2026-08-05 배포부터 쌓인다. 7월의 0은 "아무도 안 썼다"가
--     아니라 "계측기가 없었다"다. [1]번의 사용자집계_시작일을 먼저 확인하고,
--     그 앞 구간은 [3]번(행위자 복원)으로 대체해서 보고한다.
--  2) created_at 은 SQLite CURRENT_TIMESTAMP = UTC 다. 반드시
--     datetime(created_at,'localtime') 를 거쳐야 KST 날짜가 된다.
--     안 그러면 매일 오전 9시 이전 기록이 전날로 밀린다(9시간 창).
--     단 'localtime' 은 서버 시계가 KST라는 환경 가정이지 코드의 보장이 아니다.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- [1] 데이터 가용 시점 점검  ★ 항상 이것부터 돌린다
--     보고서 각주에 쓸 "언제부터 집계된 숫자인가"를 확정하는 쿼리.
-- ----------------------------------------------------------------------------
SELECT '[1] 데이터 가용 시점' AS 구분,
       (SELECT MIN(activity_date) FROM usage_events)                            AS 사용자집계_시작일,
       (SELECT MAX(activity_date) FROM usage_events)                            AS 사용자집계_최종일,
       (SELECT COUNT(*)           FROM usage_events)                            AS 사용자이벤트_총건수,
       (SELECT MIN(date(datetime(created_at,'localtime'))) FROM field_schedules) AS 일정기록_시작일,
       (SELECT MIN(date(datetime(created_at,'localtime'))) FROM audit_events)    AS 감사기록_시작일;


-- ----------------------------------------------------------------------------
-- [2] 실제로 쓰는 사람 — 월별 (usage_events 기반, 8/5 이후만 유효)
--     활성사용자 = 로그인 상태로 화면을 열었거나 일정을 등록·수정·삭제한 고유 인원
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[2] 월별 활성사용자' AS 구분,
       substr(activity_date,1,7) AS 월,
       COUNT(DISTINCT CASE WHEN actor_user NOT IN ('auto-system','system')
                           THEN actor_user END)                        AS 활성사용자,
       COUNT(DISTINCT activity_date)                                   AS 활동일수,
       SUM(CASE WHEN event_type='schedule_created' THEN 1 ELSE 0 END)  AS 일정등록,
       SUM(CASE WHEN event_type='schedule_updated' THEN 1 ELSE 0 END)  AS 일정수정,
       SUM(CASE WHEN event_type='schedule_deleted' THEN 1 ELSE 0 END)  AS 일정삭제
FROM usage_events, p
WHERE activity_date BETWEEN s AND e
GROUP BY 월
ORDER BY 월;


-- ----------------------------------------------------------------------------
-- [3] 7월 복원 — 실제로 무언가를 '한' 사람 수 (계측기 없던 구간 대체)
--     정의가 [2]와 다르다: 화면만 열어본 사람은 안 잡히므로 이 숫자는 하한선이다.
--     보고서에는 반드시 "하한"이라고 적는다.
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30')),
acts AS (
    SELECT last_actor_user AS u,
           date(datetime(COALESCE(last_actor_at, created_at),'localtime')) AS d
      FROM field_schedules WHERE TRIM(COALESCE(last_actor_user,'')) <> ''
    UNION ALL
    SELECT actor_user,  date(datetime(created_at,'localtime')) FROM audit_events  WHERE TRIM(COALESCE(actor_user,''))  <> ''
    UNION ALL
    SELECT uploaded_by, date(datetime(created_at,'localtime')) FROM photo_uploads WHERE TRIM(COALESCE(uploaded_by,'')) <> ''
    UNION ALL
    SELECT user_id,     date(datetime(created_at,'localtime')) FROM chat_events   WHERE TRIM(COALESCE(user_id,''))     <> ''
)
SELECT '[3] 월별 실행위자(하한)' AS 구분,
       substr(d,1,7)     AS 월,
       COUNT(DISTINCT u) AS 실행위자수,
       COUNT(DISTINCT d) AS 활동일수,
       COUNT(*)          AS 행위건수
FROM acts, p
WHERE u NOT IN ('auto-system','system') AND d BETWEEN s AND e
GROUP BY 월
ORDER BY 월;


-- ----------------------------------------------------------------------------
-- [4] ★ 핵심 — 손일이 얼마나 줄었나 (월별)
--     자동입력    = 공사일정계획서 사진 1장으로 일괄 등록된 건 (source_kind<>'manual')
--     ERP실적기재 = 현장 투입인원/장비가 대시보드에서 바로 입력된 건
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[4] 월별 일정·자동화' AS 구분,
       strftime('%Y-%m', datetime(created_at,'localtime')) AS 월,
       COUNT(*)                                                                  AS 등록일정,
       SUM(CASE WHEN COALESCE(source_kind,'manual')<>'manual' THEN 1 ELSE 0 END)  AS 자동입력,
       ROUND(100.0*SUM(CASE WHEN COALESCE(source_kind,'manual')<>'manual' THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*),0), 1)                                             AS 자동입력_비율,
       -- ⚠️ erp_data 는 일정을 저장하면 **전 항목이 0인 빈 껍데기 JSON**으로 채워진다.
       --    "비어 있지 않다"로 세면 매달 100%가 나온다(2026-09-18 실측으로 확인된 오집계).
       --    실제로 값이 하나라도 들어간 행만 센다.
       SUM(CASE WHEN erp_data IS NOT NULL AND json_valid(erp_data)
                 AND (SELECT COUNT(*) FROM json_each(erp_data) WHERE CAST(value AS INTEGER)<>0) > 0
                THEN 1 ELSE 0 END)                                                AS ERP실적기재,
       SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END)                    AS 이후삭제,
       COUNT(DISTINCT last_actor_user)                                            AS 입력자수
FROM field_schedules, p
WHERE date(datetime(created_at,'localtime')) BETWEEN s AND e
GROUP BY 월
ORDER BY 월;


-- ----------------------------------------------------------------------------
-- [5] 누가 쓰는가 — 사용자별 기여 (사장님이 반드시 되물어보는 질문)
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[5] 사용자별' AS 구분,
       last_actor_user                                        AS 사용자,
       COUNT(*)                                               AS 등록일정,
       COUNT(DISTINCT date(datetime(created_at,'localtime'))) AS 활동일수,
       MIN(date(datetime(created_at,'localtime')))            AS 첫활동,
       MAX(date(datetime(created_at,'localtime')))            AS 최종활동
FROM field_schedules, p
WHERE date(datetime(created_at,'localtime')) BETWEEN s AND e
  AND TRIM(COALESCE(last_actor_user,'')) <> ''
GROUP BY 사용자
ORDER BY 등록일정 DESC;


-- ----------------------------------------------------------------------------
-- [5-보강] 등록 주체 구분 — "직원이 쓴다"를 말하려면 반드시 이 구분이 필요하다
--     `last_actor_user` 에는 사람 계정만 있는 게 아니라 **1층 공용 상황판**과
--     관리자 본인 계정이 섞여 들어온다. 나누지 않으면 사용자 수가 부풀어 보인다.
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[5-보강] 주체별' AS 구분,
       CASE WHEN last_actor_user IN ('전자칠판','상황판','1층 상황판') THEN '공용 상황판'
            WHEN last_actor_user = 'admin'                            THEN '관리자(본인)'
            WHEN last_actor_user LIKE 'kakao_%'                       THEN '이름미등록 카카오'
            ELSE '현장 직원(실명)' END AS 주체,
       COUNT(*)                        AS 등록일정,
       COUNT(DISTINCT last_actor_user) AS 계정수
FROM field_schedules, p
WHERE date(datetime(created_at,'localtime')) BETWEEN s AND e
  AND TRIM(COALESCE(last_actor_user,'')) <> ''
GROUP BY 주체
ORDER BY 등록일정 DESC;


-- ----------------------------------------------------------------------------
-- [6] 자료 보전 — 일일 백업 커버리지
--     성공률만 세면 "시도조차 안 한 날"이 안 잡힌다. 그래서 달력을 만들어
--     분기 전체 일수 대비 실제 백업이 남은 날을 센다.
-- ----------------------------------------------------------------------------
-- ⚠️ 분모에서 아직 오지 않은 날을 뺀다. 백업은 '전일분'을 만드니 대상은 어제까지다.
--    안 그러면 진행 중인 달이 늘 실패한 것처럼 보인다(9월을 56.7%로 오독한 실측 사례 — 실제는 17/17=100%).
WITH RECURSIVE p(s,e) AS (SELECT '2026-07-01', MIN('2026-09-30', date('now','localtime','-1 day'))),
cal(d) AS (
    SELECT s FROM p
    UNION ALL
    SELECT date(d,'+1 day') FROM cal, p WHERE d < e
)
SELECT '[6] 백업 커버리지' AS 구분,
       substr(cal.d,1,7)                                          AS 월,
       COUNT(*)                                                   AS 대상일수,
       SUM(CASE WHEN j.target_date IS NOT NULL THEN 1 ELSE 0 END)  AS 백업생성일수,
       ROUND(100.0*SUM(CASE WHEN j.target_date IS NOT NULL THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*),0), 1)                              AS 커버리지_퍼센트
FROM cal
LEFT JOIN (SELECT DISTINCT target_date FROM export_jobs WHERE status='success') j
       ON j.target_date = cal.d
GROUP BY 월
ORDER BY 월;


-- ----------------------------------------------------------------------------
-- [7] 가입 승인 리드타임 — 요청부터 승인까지 며칠 걸렸나
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[7] 가입승인' AS 구분,
       COUNT(*)                                                                     AS 요청건수,
       SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END)                            AS 승인,
       SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END)                            AS 반려,
       SUM(CASE WHEN status='pending'  THEN 1 ELSE 0 END)                            AS 미처리,
       ROUND(AVG(CASE WHEN reviewed_at IS NOT NULL
                      THEN julianday(reviewed_at) - julianday(requested_at) END), 2) AS 평균처리_일,
       ROUND(MAX(CASE WHEN reviewed_at IS NOT NULL
                      THEN julianday(reviewed_at) - julianday(requested_at) END), 2) AS 최장처리_일
FROM login_access_requests, p
WHERE date(datetime(requested_at,'localtime')) BETWEEN s AND e;


-- ----------------------------------------------------------------------------
-- [8] 관리자 승인 큐 — 처리율
--     ⚠️ admin_requests 에는 처리 시각 컬럼이 없다(review_request 가 status 만 바꾼다).
--        그래서 리드타임은 뽑을 수 없고 처리율까지만 가능하다.
--        4분기부터 보려면 reviewed_at 컬럼 추가가 선행돼야 한다.
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[8] 승인큐' AS 구분,
       strftime('%Y-%m', datetime(created_at,'localtime'))         AS 월,
       COUNT(*)                                                    AS 접수,
       SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END)           AS 승인,
       SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END)           AS 반려,
       SUM(CASE WHEN status='pending'  THEN 1 ELSE 0 END)           AS 미처리,
       ROUND(100.0*SUM(CASE WHEN status<>'pending' THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*),0), 1)                               AS 처리율_퍼센트
FROM admin_requests, p
WHERE date(datetime(created_at,'localtime')) BETWEEN s AND e
GROUP BY 월
ORDER BY 월;


-- ----------------------------------------------------------------------------
-- [9] AI 기능 사용량 — 채팅 일정 입력 / 사진 업로드
-- ----------------------------------------------------------------------------
WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[9] AI채팅' AS 구분,
       strftime('%Y-%m', datetime(created_at,'localtime'))          AS 월,
       COUNT(*)                                                     AS 채팅건수,
       COUNT(DISTINCT user_id)                                      AS 사용자수,
       SUM(CASE WHEN response_status='success' THEN 1 ELSE 0 END)    AS 성공,
       ROUND(100.0*SUM(CASE WHEN response_status='success' THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*),0), 1)                                AS 성공률_퍼센트
FROM chat_events, p
WHERE date(datetime(created_at,'localtime')) BETWEEN s AND e
GROUP BY 월
ORDER BY 월;

WITH p(s,e) AS (VALUES ('2026-07-01','2026-09-30'))
SELECT '[9] 사진업로드' AS 구분,
       strftime('%Y-%m', datetime(created_at,'localtime')) AS 월,
       COUNT(*)                                            AS 업로드건수,
       COUNT(DISTINCT uploaded_by)                         AS 업로더수,
       ROUND(SUM(COALESCE(file_size,0))/1048576.0, 1)      AS 용량_MB
FROM photo_uploads, p
WHERE date(datetime(created_at,'localtime')) BETWEEN s AND e
GROUP BY 월
ORDER BY 월;
