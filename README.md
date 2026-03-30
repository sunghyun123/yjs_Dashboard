# yjs_Dashboard

FastAPI + SQLite 기반의 현장 일정/메모/관리 요청 대시보드입니다.

## 주요 기능

- 채팅 기반 일정 등록/조회 (`/`)
- 상황판 조회 및 편집 (`/dashboard.html`)
- 전자칠판 레거시 경로 (`/board.html` -> `/dashboard.html` 리다이렉트)
- 관리자 승인/감사 로그 (`/admin.html`)
- 이미지 업로드 분류 (`/api/vision/upload`)

## 인증/계정 정책 (초기 적응 단계)

- 초기 관리자 계정은 고정값입니다.
  - `id: admin`
  - `pw: 1234`
- 로그인 화면에서 `신규 사용자 등록`으로 일반 사용자를 즉시 생성할 수 있습니다.
- 로그인 화면에서 `계정 찾기`로 이름 기준 ID/비밀번호를 조회할 수 있습니다.
- 세션은 쿠키(`yjs_session_id`) 기반으로 동작합니다.

> 초기 적응 단계의 간소화 정책으로 계정 찾기 기능을 제공하고 있습니다.

## 빠른 시작

### 1) 설치

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2) `.env` 설정

루트에 `.env` 파일을 만들고 아래 값을 넣으세요 (`.env.example` 참고).

```bash
PROJECT_NAME=yjs_Dashboard
GEMINI_API_KEY=...
DATABASE_URL=sqlite:///schedule.db
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=*
ALLOWED_HOSTS=*
```

### 3) 실행

```bash
python main.py
```

브라우저 접속:

- 입력 화면: `http://localhost:8000/`
- 상황판: `http://localhost:8000/dashboard.html`
- 관리자: `http://localhost:8000/admin.html`
- 전자칠판 레거시 경로: `http://localhost:8000/board.html` (자동으로 상황판으로 이동)

## 외부 기기 접속

- 같은 네트워크: `http://<서버IP>:8000/`
- 외부망: Cloudflare Tunnel/ngrok 또는 포트포워딩
- 외부 공개 시 `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`를 실제 도메인으로 제한 권장

## 테스트

```bash
python -m pytest -q
```

스모크 테스트 범위:

- 정적 페이지 서빙: `/`, `/dashboard.html`, `/admin.html`, `/board.html`(리다이렉트 포함)
- 인증 흐름: 로그인/내 정보 조회/로그아웃
- 일정 생성 및 조회: `/api/schedules/execute`, `/api/schedules/today`
- 메모/작업자 상태: `/api/schedules/memos`, `/api/schedules/worker-status`
- 관리자 요청 큐: `/api/schedules/chat`, `/api/admin/requests`

테스트 파일:

- `tests/conftest.py`
- `tests/test_smoke_basic_flow.py`
