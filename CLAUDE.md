# CLAUDE.md

자원(회의실 등) 예약 관리 REST API. 백엔드 포트폴리오용 프로젝트.

## 목적과 작업 방식
- 포트폴리오 프로젝트다. 사용자가 면접에서 모든 코드를 설명할 수 있어야 한다.
  - 새 개념(락, 트랜잭션 격리 수준, 인덱스 등)을 도입할 때는 왜 그렇게 하는지, 다른 방법과 비교해 짧게 설명한다.
  - 한 번에 큰 기능을 몰아서 만들지 않는다. 기능 단위로 작게 나눠 진행하고 커밋도 그 단위로 나눈다.
- 의미 있는 문제를 해결하면 `docs/troubleshooting.md`에 문제, 원인, 해결, 배운 점을 남긴다.
- 설계 결정(DB 구조, 동시성 처리 방식 등)은 README의 해당 섹션을 갱신한다.
- 사용자와의 대화와 문서는 한국어로 작성한다. 코드 식별자는 영어, 주석은 한국어로 쓴다.

## 기술 스택
- Python 3.11, FastAPI, SQLAlchemy 2.x (ORM, `Mapped` 타입 표기 방식), PyMySQL
- MySQL 8.0 (로컬은 Windows 서비스 `MySQL80`)
- pydantic-settings로 `.env`에서 설정을 읽는다
- pytest, ruff, GitHub Actions

## 명령어 (Windows PowerShell, 프로젝트 루트 기준)
- 가상환경 Python: `.\.venv\Scripts\python.exe`
- 의존성 설치: `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
- 개발 서버: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
- 테스트: `.\.venv\Scripts\python.exe -m pytest -q`
- 린트/포맷: `.\.venv\Scripts\ruff.exe check .` / `.\.venv\Scripts\ruff.exe format .`
- 커밋 전에는 테스트, 린트, 포맷 검사를 모두 통과시킨다. CI도 같은 검사를 한다.

## 구조
- `app/main.py`: FastAPI 앱 생성, 라우터 등록
- `app/core/config.py`: 설정 (`get_settings()`)
- `app/db/session.py`: 엔진, 세션, `get_db` 의존성
- `app/api/`: 라우터 (기능별 파일)
- `tests/`: pytest. DB가 필요한 테스트는 `app.dependency_overrides[get_db]`로 세션을 바꿔 끼운다.
- `scripts/init_db.sql`: 로컬 DB와 앱 전용 사용자 생성 (root로 1회 실행)

## 규칙
- 비밀번호 같은 비밀 정보는 `.env`에만 둔다. 코드, 문서, 커밋에 넣지 않는다. 새 설정을 추가하면 `.env.example`도 함께 갱신한다.
- 의존성을 추가하면 버전을 고정해 `requirements.txt`(실행용) 또는 `requirements-dev.txt`(개발용)에 적는다.
- 커밋 메시지는 `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`, `chore: ...` 형식을 따르고, 내용은 한국어로 쓴다.
