# yjs_Dashboard

FastAPI + SQLite 기반의 현장 일정/메모/관리 요청 대시보드입니다.

## 외부 기기(다른 PC/모바일) 접속 설정

### 1) 서버 실행 설정

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

서버 실행:

```bash
python main.py
```

### 2) 같은 Wi-Fi/LAN에서 접속

- 서버 PC의 사설 IP 확인 (`ipconfig`)
- 모바일/다른 PC에서 `http://<서버IP>:8000/dashboard.html` 접속
- Windows 방화벽에서 `8000` 포트 인바운드 허용 필요

### 3) 외부 인터넷(다른 통신망)에서 접속

아래 중 한 가지가 필요합니다.

- 공유기 포트포워딩: 외부 `8000` -> 서버PC `8000`
- 또는 터널(권장): Cloudflare Tunnel / ngrok로 공개 HTTPS URL 발급

터널 사용 시 `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`에 발급 도메인을 지정하면 더 안전합니다.
예:

```bash
ALLOWED_ORIGINS=https://abc123.trycloudflare.com
ALLOWED_HOSTS=abc123.trycloudflare.com,localhost,127.0.0.1
```

## 테스트 실행 방법

아래 명령을 저장소 루트에서 실행하세요.

```bash
python -m pip install pytest python-multipart
python -m pytest -q
```

## 포함된 기본 동작 확인(스모크) 테스트

- 정적 페이지 서빙: `/`, `/dashboard.html`, `/admin.html`, `/board.html`
- 인증 흐름: 로그인/내 정보 조회/로그아웃
- 일정 생성 및 조회: `/api/schedules/execute`, `/api/schedules/today`
- 메모 및 작업자 상태: `/api/schedules/memos`, `/api/schedules/worker-status`
- 관리자 요청 큐: `/api/schedules/chat`(delete_request), `/api/admin/requests`

## 테스트 파일

- `tests/conftest.py`
- `tests/test_smoke_basic_flow.py`
