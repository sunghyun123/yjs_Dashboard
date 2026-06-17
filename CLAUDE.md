# yjs_Dashboard

현장 일정 관리 대시보드. FastAPI + SQLite 백엔드, 정적 HTML/JS 프론트엔드.

## 기술 스택

- **백엔드**: Python FastAPI, SQLite (`schedule.db`), Pydantic v2
- **프론트**: `web/` — 정적 HTML + Bootstrap CDN + 분리된 JS 모듈 (`dashboard.*.js`)
- **AI**: Google Gemini (`app/services/ai_service.py`)
- **인증**: 카카오 OAuth (`app/services/kakao_oauth.py`)
- **PWA**: `web/sw.js`, `web/site.webmanifest`

## 디렉터리 구조

```
app/
  api/          # FastAPI 라우터 (schedules, auth, admin, vision, local_apps)
  core/         # 설정(config.py), 인증 미들웨어(auth.py)
  db/
    repos/      # DB 접근 레이어 (schedule, user, admin, worker, export)
    migrations.py
    connection.py
  services/     # 비즈니스 로직 (ai, export, gdrive, erp_sync, kakao_*)
web/            # 프론트엔드 정적 파일
```

## 인증

- 카카오 OAuth 전용 — username/password 로그인 없음
- `kakao_whitelist.json`에 등록된 카카오 ID만 접근 가능 (미등록 시 pending → 관리자 승인)
- 세션 쿠키: `yjs_session_id` (HttpOnly, 기본 30일)

## 주요 설계 규칙

- **일정 삭제는 항상 소프트 삭제**: `soft_delete_schedule_by_id` 사용. 하드 삭제 금지.
- 수정/삭제 이력은 `audit_events` 테이블에 before/after JSON으로 저장
- 1시간 백그라운드 루프: 전일 백업 xlsx 생성 + 90일 경과분 ZIP 아카이브

## 환경 변수 (`.env`)

| 키 | 설명 |
|---|---|
| `DATABASE_URL` | `sqlite:///schedule.db` 형식 |
| `GEMINI_API_KEY` | Google Gemini API 키 |
| `KAKAO_REST_API_KEY` | 카카오 REST API 키 |
| `KAKAO_CLIENT_SECRET` | 카카오 클라이언트 시크릿 |
| `KAKAO_REDIRECT_URI` | 카카오 리다이렉트 URI |
| `COOKIE_SECURE` | HTTPS 환경이면 `true` |
| `APP_TIMEZONE` | 기본 `Asia/Seoul` |

## 실행

```bash
uvicorn app.main:app --reload
```
