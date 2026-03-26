# yjs_Dashboard 기능 명세서

## 1. 문서 목적

이 문서는 `yjs_Dashboard`의 현재 구현 기준 기능을 정의한다.  
대상 범위는 웹 화면, API, 인증/권한, 데이터 저장, 파일 처리, 백그라운드 작업, 테스트 범위다.

## 2. 시스템 개요

- **백엔드**: FastAPI (`main.py`)
- **데이터베이스**: SQLite (`schedule.db`)
- **AI 연동**: Google Gemini (텍스트 의도 분석, 이미지 문서 분석)
- **프론트엔드**: 정적 HTML (`index.html`, `dashboard.html`, `admin.html`, `board.html`)
- **파일 저장소**: `자동화_데이터` 디렉터리

## 3. 사용자 역할 및 권한

- **일반 사용자**
  - 로그인/로그아웃 가능
  - 일정 조회/등록 가능
  - 메모 등록, 작업자 상태 변경 가능
  - 수정/삭제는 관리자 승인 요청 형태로만 가능
- **관리자 (`role=admin`)**
  - 일반 사용자 기능 포함
  - 관리자 요청 큐 조회/승인/반려 가능
  - 수동 일일 내보내기 실행 가능

## 4. 화면 기능 명세

### 4.1 입력 화면 (`/`, `index.html`)

- 채팅 기반 일정 요청 입력
- 입력 카테고리 선택:
  - `schedule_create`
  - `memo`
  - `other`
  - `update_request`
  - `delete_request`
- 채팅 분석 결과 확인 후 실제 실행(`create/update/delete`)
- 사진 업로드 (`/api/vision/upload`) 연동
- 사진 업로드 시 카테고리 선택 모달 기반 전송(`TBM 문서/공사 일지 문서/영수증/미분류`)
- 채팅 응답 직후 상태 칩 UI로 현재 단계 표시(요청 접수/등록 확인 대기/조회 결과)

### 4.2 상황판 화면 (`/dashboard.html`)

- 오늘 일정 조회 및 렌더링
- 주기적 데이터 갱신(클라이언트에서 API 폴링)
- 로그인 세션 확인 후 데이터 접근
- 일정 필터 툴바 제공(키워드 검색, 조회 날짜, 오늘만 토글)
- 일정 카드별 `ID` 표시
- 일정 카드에서 수정 요청/삭제 요청을 직접 생성:
  - 수정 요청: 모달에서 데이터 편집 후 `/api/schedules/execute`(`action=update`) 요청
  - 삭제 요청: 확인 후 `/api/schedules/execute`(`action=delete`) 요청
  - 두 요청 모두 즉시 반영이 아니라 관리자 승인 큐로 접수

### 4.3 관리자 화면 (`/admin.html`)

- 관리자 요청 목록 조회
- 요청별 일정 후보 추천 조회
- 요청 승인/반려 처리
- 일일 내보내기 수동 실행
- 필터 조건 저장/복원(localStorage)
- 후보 선택 시 대상 일정 ID 자동 채움
- 반려 처리/일일 내보내기는 prompt가 아닌 모달 기반 입력
- 요청 카드 시각 개선(요청 타입 칩, 상태별 배지, 건수 표시)

### 4.4 전자칠판 화면 (`/board.html`)

- 템플릿 기반 액션 입력
  - 등록
  - 메모
  - 수정 요청
  - 삭제 요청
- 액션 결과를 일정 반영 또는 관리자 요청 큐로 전달
- 템플릿 전송 전 확인 모달 표시(유형/날짜/위치/제목/대상 ID)
- 전송 진행 상태 칩 표시(대기/전송 중/전송 완료/요청 접수 완료/전송 실패)

## 5. API 기능 명세

모든 `/api/*` 엔드포인트는 JSON 응답을 기본으로 한다.  
인증이 필요한 API는 세션 쿠키(`yjs_session_id`)가 필요하다.

### 5.1 인증 API (`/api/auth`)

#### `POST /api/auth/login`
- **설명**: 사용자 로그인 및 세션 발급
- **요청 필드**
  - `user_id` (string)
  - `password` (string)
  - `register_code` (string)
  - `device_name` (string, 기본값 `unknown-device`)
- **처리 규칙**
  - 사용자 존재 여부 확인
  - 비밀번호 SHA-256 해시 검증
  - 등록 코드 검증
- **응답**
  - 성공: `{message, user_id, role}` + HttpOnly 쿠키 설정
  - 실패: `401`, `403`

#### `POST /api/auth/logout`
- **설명**: 세션 종료
- **인증**: 필요
- **응답**: `{message}`

#### `GET /api/auth/me`
- **설명**: 현재 세션 사용자 정보 조회
- **인증**: 필요
- **응답**: `{user_id, role, device_name}`

### 5.2 일정 API (`/api/schedules`)

#### `POST /api/schedules/chat`
- **설명**: 채팅 문장을 분석하고 후보/응답 생성 (DB 직접 변경 없음)
- **인증**: 필요
- **요청 필드**
  - `text` (string)
  - `input_category` (enum)
- **처리 규칙**
  - `other/update_request/delete_request`: 즉시 관리자 요청 큐 등록
  - `memo`: 즉시 메모 생성
  - 그 외: AI 의도 분석 후 결과 반환
    - `search`: 일정 후보 조회
    - `update/delete`: 관리자 요청 큐 등록
    - `create` 등: `schedule_data` 생성
- **응답 필드**
  - `intent`
  - `reply_message`
  - `candidates`
  - `schedule_data`

#### `POST /api/schedules/execute`
- **설명**: 사용자 확인 후 실제 액션 실행
- **인증**: 필요
- **요청 필드**
  - `action` (`create`/`update`/`delete`)
  - `schedule_data` (선택)
  - `schedule_id` (선택)
- **처리 규칙**
  - `create`: 일정 업서트 즉시 수행
  - `update/delete`: 관리자 승인 요청 큐에 등록
- **응답**: `{message, status}`

#### `GET /api/schedules/today`
- **설명**: 상황판용 일정 목록 조회
- **인증**: 필요
- **쿼리**
  - `date` (선택)
- **응답**: `{message, count, data}`

#### `POST /api/schedules/memos`
- **설명**: 메모 생성
- **인증**: 필요
- **요청 필드**
  - `content` (string)
  - `target_date` (선택)
  - `memo_type` (선택)
  - `linked_schedule_id` (선택)
  - `visibility` (선택)
- **응답**: `{status, message, memo_id}`

#### `GET /api/schedules/memos`
- **설명**: 메모 조회
- **인증**: 필요
- **쿼리**
  - `date` (선택)
- **응답**: `{status, data}`

#### `POST /api/schedules/worker-status`
- **설명**: 작업자 상태 저장
- **인증**: 필요
- **요청 필드**
  - `user_name`
  - `status` (`사무실`/`외출`/`야간작업`)
  - `location`
  - `until_time`
  - `note`
- **응답**: `{status, message}`

#### `GET /api/schedules/worker-status`
- **설명**: 작업자 상태 조회
- **인증**: 필요
- **응답**: `{status, data}`

#### `POST /api/schedules/board/template-action`
- **설명**: 전자칠판 템플릿 액션 처리
- **인증**: 필요
- **요청 필드**
  - `action_type` (`register`/`memo`/`update_request`/`delete_request`)
  - `date`, `location`, `task`, `person`, `details`, `category`, `request_note`, `schedule_id`
- **처리 규칙**
  - `register`: 일정 즉시 등록
  - `memo`: 메모 즉시 등록
  - `update_request/delete_request`: 관리자 요청 큐 등록
- **응답**: `{status, message}`

### 5.3 비전 API (`/api/vision`)

#### `POST /api/vision/upload`
- **설명**: 이미지 업로드/분석/파일 저장
- **인증**: 필요
- **요청 형식**: `multipart/form-data`
  - `file` (필수)
  - `upload_category` (선택)
- **처리 규칙**
  - `upload_category` 존재 시:
    - `자동화_데이터/YYYY-MM-DD/<category>/`에 파일 저장
    - 업로드 메타(`photo_uploads`) 저장
  - `upload_category` 미지정 시:
    - AI 분석 후 문서 종류별 폴더 저장
    - 문서 종류가 작업일지면 ERP 형식 xlsx 생성
    - 원본 이미지 저장
- **응답**
  - `{message, folder, filename}`

### 5.4 관리자 API (`/api/admin`)

> 모든 관리자 API는 관리자 권한이 필요하다.

#### `GET /api/admin/requests`
- **설명**: 관리자 요청 목록 조회
- **쿼리**
  - `status` (기본 `pending`)
  - `requested_by` (선택)
  - `since`, `until` (선택)
- **응답**: `{status, data}`

#### `GET /api/admin/requests/{request_id}/candidates`
- **설명**: 요청 텍스트/페이로드 기반 일정 후보 추천
- **응답**: `{status, hint, data}`

#### `POST /api/admin/requests/review`
- **설명**: 관리자 요청 승인/반려
- **요청 필드**
  - `request_id`
  - `decision` (`approve`/`reject`)
  - `schedule_id` (선택)
  - `schedule_data` (선택)
  - `reason` (선택)
- **처리 규칙**
  - `reject`: 상태를 `rejected`로 변경
  - `approve`:
    - `update_request`: 일정 수정 반영
    - `delete_request`: 소프트 삭제 반영
    - 기타 요청 타입: 승인 처리만 수행
- **응답**: `{status, message}`

#### `POST /api/admin/export/daily`
- **설명**: 특정 일자의 일일 내보내기 실행
- **요청 필드**
  - `target_date` (선택, 미지정 시 전일)
- **응답**: `{status, message, data}`

## 6. 데이터 저장 명세

`DBManager` 초기화 시 다음 테이블이 생성된다.

- `field_schedules`: 일정 원본(소프트삭제, actor 정보 포함)
- `users`: 사용자 계정
- `sessions`: 로그인 세션
- `admin_requests`: 관리자 승인 요청 큐
- `photo_uploads`: 업로드 파일 메타데이터
- `memo_items`: 메모
- `worker_status`: 인원 상태
- `export_jobs`: 내보내기 실행 이력

### 6.1 일정 저장 규칙

- 핵심 동작은 `upsert_schedule`
- `date + location` 기준으로 기존 레코드 존재 시 UPDATE, 없으면 INSERT
- 생성/수정 시 actor(`actor_user`, `actor_device`) 추적

### 6.2 세션 저장 규칙

- 로그인 성공 시 랜덤 세션 ID 생성
- 쿠키 키: `yjs_session_id`
- TTL: 30일
- 세션 만료 또는 미존재 시 인증 실패(401)

### 6.3 파일 저장 규칙

- 업로드 루트: `자동화_데이터`
- 비전 카테고리 업로드: 날짜 폴더 + 카테고리 폴더
- 일일 백업 출력: `자동화_데이터/일일백업/YYYY-MM-DD`
  - `공사일정.xlsx`
  - `기타메모.xlsx`
  - `인원상태.xlsx`

## 7. 백그라운드/배치 기능

- 앱 startup 이벤트에서 `daily_export_loop` 시작
- 1시간마다 전일 내보내기 필요 여부를 확인
- 전일 성공 이력이 없으면 내보내기 실행

## 8. 설정 및 실행 환경

### 8.1 환경 변수

`app/core/config.py` 기준 필수 변수:

- `GEMINI_API_KEY`
- `DATABASE_URL`
- `PROJECT_NAME` (기본값 존재)

### 8.2 현재 구현 유의사항

- 실제 DB 연결은 여러 모듈에서 `schedule.db` 경로를 직접 사용한다.
- 따라서 `DATABASE_URL`은 현재 핵심 DB 연결 경로를 제어하지 않는다.

## 9. 예외/오류 처리 규칙

- 인증 누락/만료: `401`
- 관리자 권한 부족: `403`
- 요청 값 오류/적용 실패: `400`
- 서버 내부 예외: `500`
- 엔드포인트별 에러 메시지는 한국어 안내 문구를 기본으로 한다.

## 10. 테스트 명세

기본 스모크 테스트(`tests/test_smoke_basic_flow.py`) 기준:

- 정적 페이지 응답 검증
- 로그인/내정보/로그아웃 흐름 검증
- 일정 생성 및 조회 검증
- 메모 및 작업자 상태 흐름 검증
- 관리자 요청 큐 기본 흐름 검증

테스트 환경에서는 외부 AI 의존을 스텁으로 대체하고, 임시 DB를 사용한다.

수동 UX 검증은 `docs/UX_QA_CHECKLIST.md` 문서를 따른다.

## 11. 현재 제약 사항

- `GET /api/schedules/today`의 `date` 파라미터는 전달되지만, DB 조회 레이어에서 날짜 필터가 실질적으로 적용되지 않는다.
- `work_logs` 관련 로직은 일부 메서드가 있으나 테이블/흐름이 완결되지 않아 현재 주요 기능에 포함되지 않는다.
- CORS 설정이 `allow_origins=["*"]`로 열려 있어 운영 환경에서는 정책 재설정이 필요하다.

## 12. 비기능 요구사항(현재 구현 기준)

- **보안**
  - 세션 쿠키는 `HttpOnly` 사용
  - 권한 검증은 API 레벨에서 수행
- **추적성**
  - 주요 변경 작업은 actor 정보 기록
  - 내보내기 작업은 `export_jobs`에 성공/실패 이력 저장
- **운영성**
  - 일일 백업 자동 실행 + 수동 실행 경로 제공

---

본 문서는 현재 코드 구현을 기준으로 작성되었으며, 기능 변경 시 함께 갱신해야 한다.
