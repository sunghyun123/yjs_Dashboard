# yjs_Dashboard

FastAPI + SQLite 기반의 건설 현장 일정·상황판 관리 대시보드입니다.

## 주요 기능

| 기능 | 경로 |
|---|---|
| 운영 홈 (외출행선표, 공정률, 매출손익) | `/` |
| 상황판 (일정 조회·편집·드래그 정렬) | `/dashboard.html` |
| AI 채팅 일정 입력 | `/index.html` |
| 관리자 (승인 큐, 감사로그, 백업) | `/admin.html` |

### 세부 기능

- **카카오 OAuth 로그인** — 화이트리스트 즉시 입장 / 미등록자 관리자 승인 대기
- **AI 일정 등록** — Gemini 자연어 분석 → 사용자 확인 후 저장 (수정·삭제는 관리자 승인 큐 경유)
- **즉시 수정·삭제** — 상황판에서 직접 편집, 감사 이력(`audit_events`) 자동 기록
- **공사일정계획서 사진 추출** — 이미지 업로드 → Vision AI가 행 파싱 → 상황판 일괄 등록
- **ERP 투입실적 입력** — 일정 카드에 인원/장비 수량 직접 기재
- **구글 드라이브 사진 업로드** — 공사코드 기준 폴더 자동 생성 후 업로드
- **공사명 자동완성** — `수주대장조회.xlsx` 기반 코드·공사명 실시간 검색
- **작업자 외출·행선 현황** — 외출 종료시각 도달 시 자동 사무실 복귀
- **일일 백업** — 매 1시간 점검, 전일 백업 없으면 xlsx 자동 생성 / 90일 경과분 월별 ZIP 아카이브
- **PWA** — 모바일 홈 화면 추가 지원

## 프로젝트 구조

```
yjs_Dashboard/
├── app/
│   ├── api/            # FastAPI 라우터 (schedules, vision, auth, admin)
│   ├── core/           # 설정, 인증 미들웨어
│   ├── db/
│   │   ├── repos/      # DB 접근 레포지토리
│   │   ├── migrations.py
│   │   └── deps.py
│   └── services/       # AI, 드라이브, 백업, OAuth 서비스
├── web/                # 프론트엔드 (HTML, JS, PWA)
├── tests/
├── main.py
├── requirements.txt
├── kakao_whitelist.json
└── 수주대장조회.xlsx      # 공사명 자동완성 데이터
```

## 인증 정책

- 로그인은 **카카오 OAuth**만 사용합니다.
- 허용 사용자 목록은 루트의 `kakao_whitelist.json`에서 관리합니다.
  - 최초 관리자: `kakao_whitelist.json`에 본인 카카오 ID를 `role: "admin"`으로 등록 후 로그인
- 화이트리스트 미등록 사용자는 관리자 승인 대기 → `/admin.html`에서 승인
- 세션 쿠키(`yjs_session_id`), 기본 30일 유지

`kakao_whitelist.json` 예시:
```json
{
  "users": [
    { "kakao_id": "123456789", "user_id": "admin", "user_name": "홍길동", "role": "admin" }
  ]
}
```

## 빠른 시작

### 1) 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2) `.env` 설정

`.env.example`을 복사해서 `.env`로 저장 후 아래 값을 채웁니다.

```env
PROJECT_NAME=yjs_Dashboard
GEMINI_API_KEY=...
DATABASE_URL=sqlite:///schedule.db

# 카카오 로그인 (카카오 개발자 콘솔과 동일하게)
KAKAO_REST_API_KEY=...
KAKAO_REDIRECT_URI=http://localhost:8000/api/auth/kakao/callback

# 운영 서버에서는 아래도 설정
# COOKIE_SECURE=true
# ALLOWED_ORIGINS=https://your-domain.example
# ALLOWED_HOSTS=your-domain.example
```

구글 드라이브 연동이 필요하면 추가:

```env
GDRIVE_SHARED_DRIVE_ID=...
GDRIVE_SERVICE_ACCOUNT_FILE=path/to/sa.json  # 또는 JSON 문자열로
GDRIVE_SERVICE_ACCOUNT_JSON=...
```

### 3) 실행

```bash
python main.py
```

| URL | 화면 |
|---|---|
| `http://localhost:8000/` | 운영 홈 |
| `http://localhost:8000/dashboard.html` | 상황판 |
| `http://localhost:8000/index.html` | AI 채팅 입력 |
| `http://localhost:8000/admin.html` | 관리자 |

## 외부 접속

- 같은 네트워크: `http://<서버IP>:8000/`
- 외부망: Cloudflare Tunnel / ngrok / 포트포워딩
- 외부 공개 시 `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`를 실제 도메인으로 제한 권장

## 테스트

```bash
python -m pytest -q
```

스모크 테스트 범위:

- 정적 페이지 서빙 (`/`, `/index.html`, `/dashboard.html`, `/admin.html`, `/board.html` 리다이렉트)
- 카카오 OAuth 흐름 (로그인 / 내 정보 / 로그아웃)
- 미등록 사용자 pending → 관리자 승인 → 재로그인
- 일정 생성·조회 (`/api/schedules/execute`, `/api/schedules/today`)
- 공사일정계획서 파싱 import 및 photo_plan 승인
- 작업자 외출 상태 변경·조회
- 관리자 승인 큐 (채팅 요청 접수, 수정·삭제 승인·반려)
- 즉시 수정·삭제 권한 체크

## 백업 정책

- 일일 백업 엑셀: `uploads/YYYY-MM-DD_백업데이터.xlsx`
- 사진 증빙: `uploads/YYYY-MM-DD/<카테고리>/` 폴더에 원본 저장
- 사진 메타데이터(`file_size`, `file_sha256`)는 DB(`photo_uploads`)에 기록
- 서버 백그라운드 루프 (1시간 주기):
  - 전일 백업 누락 시 자동 생성
  - 90일 경과 일별 파일 → `uploads/archives/YYYY-MM_백업데이터.zip` 월별 압축 후 삭제
- 관리자 화면의 `백업데이터 생성` 버튼도 동일한 정책 사용
