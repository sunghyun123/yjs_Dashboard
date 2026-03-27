# yjs_Dashboard 배포/운영 런북

## 1. 목적

이 문서는 1인 운영 기준으로 `yjs_Dashboard`를 외부 서비스 형태로 운영하기 위한 실무 절차를 정의한다.

- 고정 도메인 외부 접속
- `dev/prod` 분리 운영
- 서버 PC 이관(교체) 절차
- 배포 전/후 점검 및 롤백

---

## 2. 표준 운영 모델

- `prod` 서버: 사용자 접속용 (`PORT=8000`)
- `dev` 서버: 개발/검증용 (`PORT=8001`)
- 외부 공개: Cloudflare Tunnel + 고정 도메인
- 원칙: 터널은 `prod`만 연결, `dev`는 내부 전용

---

## 3. 사전 준비 체크리스트

### 3.1 인프라/도메인

- [ ] 도메인 준비 완료
- [ ] Cloudflare 계정 및 DNS 관리 권한 확보
- [ ] 운영 서버 시간 동기화(NTP) 정상

### 3.2 서버 소프트웨어

- [ ] Python 설치
- [ ] 가상환경 생성
- [ ] 의존성 설치: `pip install -r requirements.txt`

### 3.3 필수 파일/데이터

- [ ] `.env` 준비
- [ ] `schedule.db` 준비
- [ ] `자동화_데이터` 디렉터리 준비

---

## 4. 환경변수 기준값

운영(`prod`) 예시:

```bash
ENV=prod
PROJECT_NAME=yjs_Dashboard
GEMINI_API_KEY=...
DATABASE_URL=sqlite:///schedule.db
INITIAL_ADMIN_PASSWORD=...
INITIAL_REGISTER_CODE=...
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=https://your-domain.example
ALLOWED_HOSTS=your-domain.example,localhost,127.0.0.1
```

개발(`dev`) 예시:

```bash
ENV=dev
PROJECT_NAME=yjs_Dashboard
GEMINI_API_KEY=...
DATABASE_URL=sqlite:///schedule.db
HOST=127.0.0.1
PORT=8001
ALLOWED_ORIGINS=http://localhost:8001
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

## 5. 배포 표준 절차

### 5.1 배포 전

- [ ] 최신 코드 반영
- [ ] 테스트 실행: `python -m pytest -q`
- [ ] DB 백업 생성 (`schedule.db` 사본 보관)
- [ ] `.env` 값 점검 (`ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, `PORT`)

### 5.2 dev 검증

- [ ] `dev` 서버 실행 (`8001`)
- [ ] 로그인/일정 조회/메모/관리자 승인/사진 업로드 점검
- [ ] 오류 로그 확인

### 5.3 prod 반영

- [ ] `prod` 서버 실행 (`8000`)
- [ ] Cloudflare Tunnel 연결 대상 확인
- [ ] 사용자 핵심 시나리오 5분 점검

---

## 6. Cloudflare Tunnel 운영 절차

### 6.1 초기 연결

- [ ] Tunnel 생성
- [ ] 도메인 레코드와 Tunnel 매핑
- [ ] 서비스 대상 `http://localhost:8000` 지정

### 6.2 운영 확인

- [ ] 외부 URL 접속 가능 확인
- [ ] 세션 로그인/로그아웃 정상
- [ ] 관리자 화면 접근 통제 정상

### 6.3 자동 시작

- [ ] OS 재부팅 후 Tunnel 자동 시작 설정
- [ ] 재부팅 후 외부 접속 재검증

---

## 7. 서버 PC 이관 절차

## 7.1 사전 준비

- [ ] 대상 PC에 Python/가상환경/의존성 설치
- [ ] 운영 계정 및 디렉터리 권한 준비

### 7.2 데이터 이전

- [ ] 소스 코드 복사
- [ ] `.env` 복사
- [ ] `schedule.db` 복사
- [ ] `자동화_데이터` 복사

### 7.3 신규 서버 기동

- [ ] `dev`로 먼저 기동 후 점검
- [ ] `prod` 기동 후 로컬 점검

### 7.4 트래픽 전환

- [ ] Tunnel 대상 서버를 신규 PC로 변경
- [ ] 외부 접속/핵심 기능 점검

### 7.5 롤백 준비

- [ ] 이전 서버를 즉시 재기동 가능한 상태로 유지
- [ ] 문제 발생 시 Tunnel 대상을 이전 서버로 복귀

---

## 8. 장애 대응 기본 규칙

- 원칙: 데이터 보호 > 빠른 복구
- 우선 확인:
  - [ ] FastAPI 프로세스 살아있는지
  - [ ] Tunnel 연결 상태 정상인지
  - [ ] `schedule.db` 파일 접근 권한/잠금 상태
  - [ ] 최근 배포 변경사항
- 복구 순서:
  1. 서비스 재기동
  2. Tunnel 재연결
  3. 필요 시 직전 백업으로 복원

---

## 9. 정기 운영 점검 (주 1회 권장)

- [ ] 테스트 실행
- [ ] DB 백업 파일 생성 및 복구 리허설
- [ ] 불필요 계정/권한 점검
- [ ] 로그의 반복 에러 점검
- [ ] 디스크 용량 점검 (`자동화_데이터` 증가량 확인)

---

## 10. 운영 원칙 요약

- 외부 공개는 `prod`만
- 개발은 항상 `dev`에서 검증 후 반영
- 배포 전 백업 필수
- 서버 이관은 "복제 후 전환" 방식으로 진행
