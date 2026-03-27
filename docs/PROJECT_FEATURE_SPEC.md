# yjs_Dashboard 프로젝트 전체 기능 명세서

## 1. 문서 목적

본 문서는 `yjs_Dashboard` 저장소의 현재 구현 기준 전체 기능을 단일 문서로 정의한다.

- 대상: 화면 기능, API, 인증/권한, 데이터 저장, 운영/배포 고려사항
- 기준: 현재 저장소 코드 및 테스트 통과 기준

---

## 2. 시스템 개요

- 백엔드: FastAPI (`main.py`)
- 데이터베이스: SQLite (`DATABASE_URL` 기반, 기본 `schedule.db`)
- 프론트엔드: 정적 HTML (`index.html`, `dashboard.html`, `admin.html`, `board.html`)
- AI:
  - 텍스트 의도 분석: Gemini (`app/services/ai_service.py`)
  - 이미지 문서 분석: Gemini (`app/services/vision_ai_service.py`)
- 파일 저장소: `자동화_데이터`

---

## 3. 사용자 역할

### 3.1 일반 사용자

- 로그인/로그아웃 가능
- 일정 등록/조회 가능
- 메모 등록/조회/삭제 가능
- 외출/야간/사무실 상태 등록/조회/삭제 가능
- 채팅/전자칠판 템플릿 입력 가능

### 3.2 관리자

- 일반 사용자 기능 포함
- 관리자 요청 큐 조회/승인/반려 가능
- 승인 요청 후보 일정 추천 조회 가능
- 감사 로그 조회 가능
- 현장직 이름 목록 등록/삭제 가능
- 일일 내보내기 수동 실행 가능

---

## 4. 화면 기능

## 4.1 입력 화면 (`/`, `index.html`)

- 로그인 오버레이 제공
- 채팅 입력 카테고리:
  - `schedule_create`
  - `memo`
  - `other`(관리자 전송)
- 채팅 응답 상태 칩 표시:
  - 요청 접수
  - 등록 확인 대기
  - 조회 결과
- 사진 업로드:
  - 업로드 카테고리 모달 제공
  - `TBM 문서`, `공사 일지 문서`, `영수증`, `미분류`

## 4.2 상황판 (`/dashboard.html`)

- 일정 목록 조회 및 렌더링
- 기본 조회 정책:
  - `오늘만` ON: 당일 조회
  - `오늘만` OFF: 과거 3일 + 오늘 + 미래 7일 윈도우 조회
- 검색/날짜/오늘만 필터 제공
- 일정 카드 액션:
  - 즉시 수정
  - 즉시 삭제
  - 메모 작성(일정 연결 메모)
  - 작업 인원 추가
- 카드 드래그 정렬 및 배치 저장(`reorder-batch`)
- 외출/행선표 상태 조회
- 일반 메모 등록/조회/삭제
- 전자칠판 템플릿 입력 지원

## 4.3 관리자 화면 (`/admin.html`)

- 관리자 권한 검증
- 요청 큐 필터 조회:
  - 상태/요청자/기간
- 요청 승인/원클릭 승인/반려
- 요청별 후보 일정 추천 및 선택
- 승인 상태(`approved`) 조회 시:
  - 현재 반영 컨텐츠 스냅샷 조회
  - 감사 로그(즉시 수정/삭제 이력) 조회
- 현장직 이름 목록 관리
- 일일 내보내기 실행

## 4.4 전자칠판 (`/board.html`)

- 일정/상태/메모 통합 표시
- 상태 빠른 변경:
  - 사무실/외출/야간작업
- 상태 항목별 삭제 가능
- 일정 인라인 즉시 수정/삭제
- 일정 연결 메모 작성
- 템플릿 입력 + 전송 확인 모달

---

## 5. API 명세

## 5.1 인증 API (`/api/auth`)

### `POST /api/auth/login`

- 요청: `user_id`, `password`, `register_code`, `device_name`
- 처리:
  - 계정 확인
  - 비밀번호 해시 검증
  - 등록 코드 검증
- 응답:
  - 성공 시 세션 쿠키(`yjs_session_id`) 발급
  - 실패 시 `401` 또는 `403`

### `POST /api/auth/logout`

- 인증 필요
- 세션 삭제 및 쿠키 제거

### `GET /api/auth/me`

- 인증 필요
- 현재 사용자 정보 반환(`user_id`, `role`, `device_name`)

## 5.2 일정 API (`/api/schedules`)

### `POST /api/schedules/chat`

- 사용자 자연어 분석
- 카테고리별 처리:
  - `other`: 관리자 요청 큐 접수
  - `memo`: 즉시 메모 생성
  - `schedule_create`: AI 의도 분석 후 `create/search/incomplete` 등 반환
- DB 직접 변경은 제한적(메모/큐 접수 제외)

### `POST /api/schedules/execute`

- 사용자 확인 후 실행
- `create`: 즉시 일정 반영(`upsert_schedule`)
- `update/delete`: 관리자 요청 큐 접수

### `GET /api/schedules/today`

- 조회 파라미터 `date`가 있으면 해당 날짜 조회
- 없으면 일정 윈도우(과거3/미래7) 조회

### `GET /api/schedules/field-staff`

- 현장직 이름 목록 조회

### `POST /api/schedules/memos`

- 메모 생성
- `linked_schedule_id`로 일정 귀속 메모 지원

### `GET /api/schedules/memos`

- 메모 조회(`date` 필터 가능)

### `DELETE /api/schedules/memos/{memo_id}`

- 메모 소프트 삭제

### `POST /api/schedules/worker-status`

- 상태 저장/갱신

### `GET /api/schedules/worker-status`

- 상태 조회(자동 복귀 처리 포함)

### `DELETE /api/schedules/worker-status/{user_name}`

- 상태 항목 삭제

### `POST /api/schedules/board/template-action`

- 전자칠판 템플릿 처리
- `register`: 즉시 일정 등록
- `memo`: 즉시 메모 등록

### `POST /api/schedules/direct-update`

- 일정 즉시 수정
- 감사 로그 기록(`audit_events`)

### `POST /api/schedules/direct-delete`

- 일정 즉시 소프트 삭제
- 감사 로그 기록(`audit_events`)

### `POST /api/schedules/reorder-batch`

- 드래그 정렬 결과 일괄 반영

## 5.3 비전 API (`/api/vision`)

### `POST /api/vision/upload`

- 인증 필요
- `multipart/form-data`
- `upload_category`가 있으면:
  - `자동화_데이터/YYYY-MM-DD/<category>/` 저장
  - 업로드 메타(`photo_uploads`) 저장
- `upload_category`가 없으면:
  - AI 문서 분석
  - 문서 유형별 저장
  - 작업일지면 ERP 형식 xlsx 생성

## 5.4 관리자 API (`/api/admin`)

### `GET /api/admin/requests`

- 관리자 요청 목록 조회

### `GET /api/admin/requests/{request_id}/candidates`

- 요청 기반 일정 후보 추천

### `POST /api/admin/requests/review`

- 요청 승인/반려
- update/delete 승인 시 실제 반영 수행

### `GET /api/admin/audit-events`

- 감사 로그 조회(행위/기간 필터)

### `POST /api/admin/field-staff`

- 현장직 이름 추가

### `DELETE /api/admin/field-staff/{staff_id}`

- 현장직 이름 삭제

### `POST /api/admin/export/daily`

- 특정 날짜 일일 내보내기 실행

---

## 6. 데이터 저장 명세

주요 테이블:

- `field_schedules`
- `users`
- `sessions`
- `admin_requests`
- `photo_uploads`
- `memo_items`
- `worker_status`
- `export_jobs`
- `field_staff`
- `audit_events`

핵심 규칙:

- 일정 삭제는 소프트 삭제(`deleted_at` 등)
- 일정/메모/상태 변경 시 actor 정보 기록
- 즉시 수정/삭제는 `audit_events`에 before/after 저장

---

## 7. 인증/세션 명세

- 세션 쿠키 이름: `yjs_session_id`
- 세션 TTL: 30일
- 로그인 성공 시 HttpOnly 쿠키 발급
- 권한 검증:
  - 일반 인증: `require_session`
  - 관리자 인증: `require_admin`

---

## 8. 배치/백그라운드 기능

- 앱 시작 시 `daily_export_loop` 실행
- 1시간 주기로 전일 내보내기 필요 여부 점검
- 전일 성공 이력이 없으면 자동 내보내기 실행

---

## 9. 운영/배포 기능 요약

- DB 경로는 `DATABASE_URL` 기반
- 운영 전환 권장:
  - 고정 도메인 + 터널 방식
  - dev/prod 분리 운영
- 런북 문서:
  - `docs/DEPLOY_RUNBOOK.md`

---

## 10. 오류 처리 원칙

- 인증 누락/만료: `401`
- 권한 부족: `403`
- 요청 데이터 오류: `400`
- 서버 내부 오류: `500`

---

## 11. 테스트 범위

기본 스모크 테스트 파일:

- `tests/conftest.py`
- `tests/test_smoke_basic_flow.py`

검증 범위:

- 정적 페이지 응답
- 로그인/로그아웃/내정보
- 일정 생성 및 조회
- 메모/상태 기본 흐름
- 관리자 요청 큐 기본 흐름

---

## 12. 현재 제약 사항

- 단일 SQLite 기반으로 대규모 동시성에는 한계가 있다.
- 프론트엔드가 정적 HTML + 인라인 JS 중심이라 대형 기능 확장 시 모듈화가 필요하다.
- 운영 보안 수준은 환경변수(`ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, 쿠키 정책) 설정에 크게 의존한다.

---

본 문서는 저장소 현재 상태 기준이며, 기능 변경 시 함께 갱신해야 한다.
