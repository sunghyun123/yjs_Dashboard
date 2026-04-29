# yjs_Dashboard 레포지토리 상세 설명서

이 문서는 `yjs_Dashboard`의 **실제 코드 기준** 동작을 정리한 운영/개발 설명서입니다.  
특히 "무엇이 되는지"와 "어떤 흐름으로 돌아가는지"를 세세하게 이해할 수 있도록 작성했습니다.

---

## 1) 프로젝트 한 줄 요약

`yjs_Dashboard`는 현장 일정 관리, 관리자 승인, 사진/문서 AI 분석, 증빙/백업 생성을 하나로 묶은 **FastAPI + SQLite 기반 현장 운영 대시보드**입니다.

- 백엔드: Python `FastAPI`
- 데이터 저장소: `SQLite`
- AI: Google Gemini (자연어 의도 분석 + 문서/이미지 추출)
- 프론트: 정적 HTML/JS 페이지를 FastAPI가 직접 서빙

---

## 2) 시스템 전체 구조

### 2-1. 실행 진입점

- 서버 시작 파일: `main.py`
- FastAPI 앱 생성 후 라우터 등록:
  - `app/api/schedules.py`
  - `app/api/vision.py`
  - `app/api/auth.py`
  - `app/api/admin.py`
  - `app/api/documents.py`
  - `app/api/local_apps.py`
- 백그라운드 루프:
  - `daily_export_loop()`가 1시간마다 전일 백업 생성 여부 확인
  - 90일 지난 일별 백업 파일은 월 단위 ZIP 아카이브

### 2-2. 프론트/백엔드 관계

- FastAPI가 다음 페이지를 그대로 반환:
  - `home.html` (기본 `/`)
  - `dashboard.html`
  - `index.html`
  - `admin.html`
- 화면 JS:
  - `dashboard.auth.js`
  - `dashboard.schedule.js`
  - `dashboard.sidebar.js`
  - `dashboard.document.js`
  - `home.js`

즉, 별도의 프론트 빌드 서버 없이 **백엔드 하나로 화면+API를 함께 제공**하는 구조입니다.

---

## 3) 핵심 도메인 기능 설명

## 3-1. 인증/권한 (카카오 OAuth + 세션 쿠키)

관련 파일:
- `app/api/auth.py`
- `app/core/auth.py`
- `app/services/kakao_oauth.py`
- `app/services/kakao_whitelist.py`

동작 방식:
- 로그인 방식은 카카오 OAuth 기반입니다.
- `/api/auth/kakao/login` 호출 시 카카오 인증 페이지로 이동합니다.
- 콜백(`/api/auth/kakao/callback`)에서 카카오 사용자 확인 후 세션 쿠키 `yjs_session_id`를 발급합니다.
- 세션은 DB `sessions` 테이블에 저장되고 만료 정책(30일)을 따릅니다.
- 권한:
  - `require_session`: 로그인 필요
  - `require_admin`: 관리자 권한 필요

특징:
- 카카오 사용자 화이트리스트 또는 승인 요청(`login_access_requests`) 기반으로 접근 제어
- 승인 전 계정은 pending 상태로 대기
- 쿠키는 HttpOnly + SameSite 설정, 운영 시 `COOKIE_SECURE=true` 권장

---

## 3-2. 일정 관리 (핵심 업무 기능)

관련 파일:
- `app/api/schedules.py`
- `app/db/db_manager.py`
- `app/services/ai_service.py`

### A. 채팅 기반 의도 분석 (`POST /api/schedules/chat`)

입력:
- `text`: 사용자 자연어
- `input_category`: 공사/일정/기타 요청 분류

동작:
- Gemini가 메시지를 `create / update / delete / search / incomplete`로 분류
- 결과로 `schedule_data`, `target_date`, `target_keyword`, `reply_message`를 생성
- update/delete/기타 요청은 바로 반영하지 않고 관리자 승인 큐(`admin_requests`)로 전송

출력:
- `intent`, `reply_message`, `candidates`, `schedule_data`

핵심 포인트:
- AI가 DB를 직접 변경하지 않음
- 사용자가 후속 버튼(등록/수정/삭제 실행)을 눌러야 실제 반영됨

### B. 실제 반영 (`POST /api/schedules/execute`)

입력:
- `action`: create/update/delete
- create 시 `schedule_data`
- update/delete 시 `schedule_id` 또는 변경 데이터

동작:
- `create`: 즉시 DB 반영(`upsert_schedule`)
- `update/delete`: 관리자 승인 큐로 접수

### C. 상황판 조회 (`GET /api/schedules/today`)

조회 방식:
- `range_start`, `range_end` 전달 시 범위 조회
- `date` 전달 시 특정 날짜 조회
- 파라미터 없으면 기본 윈도우 조회(과거 3일 ~ 미래 7일)

### D. 즉시 수정/삭제 (관리 추적 포함)

- `POST /api/schedules/direct-update`
- `POST /api/schedules/direct-delete`

특징:
- 요청 성공 시 `audit_events`에 before/after 데이터 기록
- 추적 가능한 운영 이력 관리 가능

### E. 순서 변경 / 템플릿 액션 / 계획서 반영

- `POST /api/schedules/reorder-batch`
  - 드래그 정렬 결과를 `display_order`로 저장
- `POST /api/schedules/board/template-action`
  - 전자칠판 연동 템플릿 액션 처리
- `POST /api/schedules/import-construction-plan`
  - 추출된 계획서 표 행을 일정으로 일괄 등록
- `POST /api/schedules/acknowledge-photo-plan`
  - 사진 추출 일정의 "검토 완료" 처리

---

## 3-3. 작업자 상태 관리 (외출/사무실/휴가/야간)

관련 파일:
- `app/api/schedules.py`
- `app/db/db_manager.py`

엔드포인트:
- `POST /api/schedules/worker-status`
- `GET /api/schedules/worker-status`
- `DELETE /api/schedules/worker-status/{user_name}`

특징:
- 상태 값: `사무실`, `외출`, `야간작업`, `휴가`
- `until_time`이 지난 외출은 조회 시 자동으로 사무실 복귀 처리 (`apply_outing_auto_return`)
- 자동 복귀 내역도 audit 이벤트로 기록

---

## 3-4. 관리자 기능 (요청 승인/감사/마스터 관리)

관련 파일:
- `app/api/admin.py`
- `app/db/db_manager.py`

주요 기능:
- 요청 큐 조회: `GET /api/admin/requests`
- 요청 후보 추천: `GET /api/admin/requests/{id}/candidates`
- 요청 승인/반려: `POST /api/admin/requests/review`
- 감사 로그 조회: `GET /api/admin/audit-events`
- 카카오 로그인 승인 요청 처리:
  - `GET /api/admin/login-access-requests`
  - `POST /api/admin/login-access-requests/{id}/review`
- 마스터 데이터 관리:
  - 현장직(`field_staff`) CRUD
  - 외출 인원(`outing_staff`) CRUD
  - 자주 가는 사이트(`frequent_sites`) CRUD
- 백업 강제 실행: `POST /api/admin/export/daily`

---

## 3-5. 이미지 업로드/문서 분류 (Vision API)

관련 파일:
- `app/api/vision.py`
- `app/services/vision_ai_service.py`

엔드포인트:
- `POST /api/vision/extract-worklog`
  - 작업일지 이미지에서 인력/장비 항목 추출
  - ERP 형태 row 데이터로 변환해 반환
- `POST /api/vision/upload`
  - (1) 카테고리 지정 업로드 또는 (2) AI 자동 분류 업로드
  - 파일 SHA-256, 파일 크기, 업로더 정보를 DB에 기록

저장 구조:
- `자동화_데이터/YYYY-MM-DD/<카테고리>/...`

---

## 3-6. 문서 템플릿 생성/추출 (Documents API)

관련 파일:
- `app/api/documents.py`
- `app/services/document_ai_service.py`
- `app/services/document_templates_service.py`
- `document_templates/`

엔드포인트:
- `GET /api/documents/templates`
  - 템플릿/필드 메타 조회
- `POST /api/documents/suggest`
  - 필수 게이트 통과 후 AI 추천값 생성
- `POST /api/documents/fill`
  - 템플릿에 값 채워 파일 반환
- `POST /api/documents/extract`
  - 이미지에서 필드 또는 표(table) 추출
- `POST /api/documents/export-table`
  - 추출한 표 데이터를 xlsx 파일로 내보내기

보안 포인트:
- 템플릿 파일 경로는 `resolve_template_file`로 루트 밖 접근 차단

---

## 3-7. 로컬 EXE 실행 (운영 PC 보조기능)

관련 파일:
- `app/api/local_apps.py`
- `app/core/config.py`

엔드포인트:
- `POST /api/local/launch` (`hangul` 또는 `erp`)

특징:
- 서버와 같은 PC에서만 동작하는 로컬 프로그램 실행 API
- `.env`의 `LOCAL_APPS_ROOT` 설정 시 활성화
- 경로 탐색 문자(`..`, `/`, `\`) 차단으로 안전성 강화

---

## 4) 데이터베이스 구조 (SQLite)

핵심 파일:
- `app/db/db_manager.py`

주요 테이블:
- `field_schedules` 일정 원본(soft delete, source_kind, display_order 포함)
- `users` 사용자
- `sessions` 세션
- `login_access_requests` 카카오 승인 요청
- `admin_requests` 관리자 승인 큐
- `worker_status` 인원 상태
- `photo_uploads` 업로드 파일 메타
- `audit_events` 감사 로그
- `chat_events` AI 채팅 이벤트 로그
- `field_staff`, `outing_staff`, `frequent_sites` 마스터
- `export_jobs` 백업 작업 이력

특징:
- 앱 시작 시 마이그레이션 성격의 컬럼 추가 로직 수행
- 단일 파일 DB라 구축/복구가 쉬우나, 대규모 동시성에는 한계가 있음

---

## 5) 백업/아카이브 정책

관련 파일:
- `main.py`
- `app/services/export_service.py`
- `app/api/admin.py`

정책:
- 전일 데이터 백업 파일 생성
- 오래된 일별 파일(90일 초과)은 월별 ZIP로 압축
- 자동 백그라운드 루프 + 관리자 수동 실행 둘 다 지원

---

## 6) 보안 설정 포인트

관련 파일:
- `main.py`
- `app/core/config.py`
- `app/core/auth.py`
- `app/api/local_apps.py`

적용 항목:
- `TrustedHostMiddleware`
- `SecurityHeadersMiddleware` (`X-Frame-Options`, `nosniff` 등)
- 선택적 HTTPS 리다이렉트 (`FORCE_HTTPS_REDIRECT`)
- 세션 쿠키 보안 플래그 (`COOKIE_SECURE`)

운영 권장:
- `ALLOWED_ORIGINS=*`, `ALLOWED_HOSTS=*`를 실제 도메인으로 제한
- HTTPS 환경에서 `COOKIE_SECURE=true` 사용

---

## 7) 환경변수(.env) 핵심 설명

정의 파일:
- `app/core/config.py`

주요 값:
- `GEMINI_API_KEY`: AI 기능 필수
- `DATABASE_URL`: `sqlite:///schedule.db` 형태 사용
- `HOST`, `PORT`: 서버 실행 주소
- `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`: CORS/Host 허용 제어
- `KAKAO_REST_API_KEY`, `KAKAO_REDIRECT_URI`: 카카오 로그인
- `COOKIE_SECURE`, `FORCE_HTTPS_REDIRECT`: 배포 보안
- `DOCUMENT_TEMPLATES_DIR`: 문서 템플릿 루트
- `LOCAL_APPS_ROOT`: 로컬 EXE 실행 루트
- `APP_TIMEZONE`: 외출 복귀 비교 기준 타임존

---

## 8) 실행/개발 기본 가이드

### 8-1. 로컬 실행

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

접속:
- `http://localhost:8000/` (home)
- `http://localhost:8000/dashboard.html`
- `http://localhost:8000/index.html`
- `http://localhost:8000/admin.html`

### 8-2. 테스트

```bash
python -m pytest -q
```

테스트 파일:
- `tests/conftest.py`
- `tests/test_smoke_basic_flow.py`

---

## 9) 문서/코드 간 차이(중요)

현재 코드 기준으로 확인된 차이:
- 기존 README의 "id/pw 직접 로그인, 회원가입, 계정찾기" 설명은 현재 구현과 다릅니다.
- 실제 인증 흐름은 카카오 OAuth + 세션 기반입니다.
- `/api/auth/login`, `/api/auth/signup`, `/api/auth/find-account`류 엔드포인트는 현재 코드에 없습니다.
- `today` 기본 조회 범위는 과거 3일/미래 7일입니다.

즉, 기능 이해/개발 시에는 README 일부보다 **API 코드(`app/api/*.py`)를 우선 신뢰**해야 합니다.

---

## 10) 이 레포를 처음 보는 개발자를 위한 빠른 이해 순서

1. `main.py`로 전체 라우터와 런타임 구조 파악  
2. `app/api/schedules.py`로 핵심 비즈니스 흐름 파악  
3. `app/db/db_manager.py`로 실제 데이터 구조와 저장 규칙 확인  
4. `app/api/auth.py` + `app/core/auth.py`로 인증/권한 모델 이해  
5. `app/api/admin.py`로 운영 승인/감사 흐름 파악  
6. `app/api/vision.py`, `app/api/documents.py`로 AI 부가 기능 확장 범위 파악

---

## 11) 앞으로 유지보수할 때 꼭 기억할 것

- 이 시스템의 핵심 안정성은 "즉시 반영"과 "승인 큐 반영"을 구분하는 정책에서 나옵니다.
- AI는 보조 판단 도구이며, 최종 반영은 사용자/관리자 승인 단계에서 통제됩니다.
- 변경 이력(`audit_events`)을 반드시 남기는 방향으로 기능을 확장해야 운영 추적성이 유지됩니다.
- 보안 배포 시 CORS/Host/Cookie/HTTPS 설정을 먼저 점검해야 합니다.

---

## 12) ERP 연동 개발 예정사항 (`erp-api-demo.html` 기준)

이 섹션은 `erp-api-demo.html`에 구현된 **시연용 UI 초안**을 기준으로 정리한 "향후 실제 개발 계획"입니다.  
중요한 점은, 현재 데모 화면은 UX/흐름 확인 목적이며 ERP 실서버 연동 코드는 아직 본격 구현 전이라는 것입니다.

### 12-1. 목표 시나리오 (사용자 흐름)

예정 사용자 흐름은 다음 4단계입니다.

1) 로그인  
2) 메인 메뉴 진입  
3) `전송 데이터 등록` 또는 `ERP 정보 조회` 선택  
4) 명시적 버튼 클릭으로만 전송/조회 실행

핵심 정책:
- 조회 화면은 진입 시 자동 호출하지 않고, 반드시 `조회` 버튼을 눌러야 GET 요청 실행
- 전송 화면은 `전송` 버튼을 눌러야 POST 요청 실행

### 12-2. 전송 데이터 등록 기능 (예정)

데모 기준 확정된 입력 기능:
- 전송 구분 선택:
  - `투입 실적 등록`
  - `자재비 등록`
  - `관리비 등록`
- 엑셀 파일 선택 후 전송 버튼
- 수기 입력 폼으로 단건 JSON 전송
- 요청 JSON 프리뷰/처리 로그 표시

투입실적 데이터 구조(예정):
- 필수: `work_code`(지중 No), `input_date`(투입일)
- 인력/장비 항목: 주간/야간 분리 수량
  - 예: `regular_day`, `regular_night`, `dump15t_day`, `dump15t_night` 등
- 외주 항목: 단일 수량
  - `outsource_1`, `outsource_2`
- 미입력 수량은 0으로 처리

예정 API(데모 기준):
- `POST /erp/work-input-records`
  - 요청: `{ transfer_type, request_time, record }`
  - 응답: 전송 성공/실패 메시지 + 필요 시 에러 코드

### 12-3. 작업일지 AI 자동채움 연계 (예정)

이미 레포에 있는 기능과 ERP 전송을 연결하는 계획:
- 이미지 업로드 → `POST /api/vision/extract-worklog`
- 추출 결과를 ERP 단건 입력 폼에 자동 반영
- 사용자가 검토 후 ERP 전송 버튼으로 최종 전송

데모 화면의 현재 동작:
- 실 API 호출 실패 시 데모 추출값(`fallback`) 자동 대체

실개발 예정 포인트:
- 실패 원인(미로그인, 파싱오류, API 응답오류) 구분 표시
- 추출값 검증(필수값/음수/이상치) 추가
- 자동채움 후 수정 이력을 남길지(audit) 정책 결정

### 12-4. ERP 정보 조회(공정률) 기능 (예정)

데모 기준 화면 요구사항:
- 현장 선택
- 공사(지중번호) 선택
  - 공사 건수가 적으면 콤보박스
  - 공사 건수가 많으면 코드헬프 팝업(부분검색 LIKE)
- `조회` 버튼 클릭 시 공정률 조회 실행

예정 API(데모 기준):
- `GET /erp/project-progress?work_code=...`
  - 응답 예: `{ work_code, project_name, achievement_rate, accumulated_amount, result, message }`

조회 결과 UI:
- KPI 표시: 지중No, 달성률(%), 누적기성
- 진행률 바 업데이트
- 요청/응답 JSON 프리뷰 제공

### 12-5. 백엔드 구현 예정 작업 체크리스트

1) ERP 연동 라우터 신설 (`app/api/erp.py` 권장)  
2) 전송 API 구현: `POST /erp/work-input-records`  
3) 조회 API 구현: `GET /erp/project-progress`  
4) 코드헬프용 공사 목록 API 추가 검토 (예: 코드/공사명 LIKE 검색)  
5) 엑셀 업로드 파서 구현 (`transfer_type`별 컬럼 매핑)  
6) ERP 외부 API 실패/타임아웃/재시도 정책 수립  
7) ERP 요청/응답 감사로그(마스킹 포함) 저장  
8) 인증/권한 정책 확정 (누가 조회/전송 가능한지)  

### 12-6. 현재 구조와의 연결 포인트

- 기존 재사용 가능:
  - `app/api/vision.py` (`/api/vision/extract-worklog`)
  - 세션 인증(`require_session`)
  - 감사 로그 테이블(`audit_events`)과 운영 패턴
- 신규 필요:
  - ERP 전용 서비스 레이어 (`app/services/erp_service.py` 권장)
  - ERP 명세서 기반 DTO/검증 스키마(pydantic)
  - ERP 장애 대응(서킷 브레이커까지는 아니어도 최소 타임아웃/에러코드 표준화)

### 12-7. 단계별 개발 제안 (현실적인 순서)

1단계 (MVP):
- 수기 입력 전송 API 1개 + 공정률 조회 API 1개
- 프론트 `erp-api-demo.html`에서 실제 API 연결

2단계:
- 엑셀 전송(파싱+검증) 구현
- 코드헬프 검색 API 구현

3단계:
- AI 자동추출 → 자동채움 → ERP 전송 완전 자동 파이프라인 안정화
- 실패 복구 UX/로그/재전송 기능 강화

---

### 12-8. 문서 상태 표기

- `erp-api-demo.html`은 **요구사항 시연용 초안**입니다.
- 본 문서의 ERP 섹션은 "현재 확정된 UI/흐름" + "예정 백엔드 작업"을 구분해 기록했습니다.
- 실제 ERP 서버 명세 변경 시, 이 섹션과 API 스키마를 함께 갱신해야 합니다.

