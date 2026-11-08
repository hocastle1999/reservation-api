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
- DB 마이그레이션 적용: `.\.venv\Scripts\alembic.exe upgrade head`
- 모델 변경 후 마이그레이션 생성: `.\.venv\Scripts\alembic.exe revision --autogenerate -m "설명"`
  - 생성된 파일은 반드시 읽고 고친 뒤, `upgrade head` → `downgrade -1` → `upgrade head` 왕복을 실제 MySQL에서 확인한다. (자동 생성된 downgrade가 MySQL에서 실패한 적이 있음: docs/troubleshooting.md)
  - `alembic.exe check`로 모델과 DB가 일치하는지 확인한다.
- 커밋 전에는 테스트, 린트, 포맷 검사를 모두 통과시킨다. CI도 같은 검사를 한다.

## 구조
- `app/main.py`: FastAPI 앱 생성, 라우터 등록
- `app/core/config.py`: 설정 (`get_settings()`)
- `app/db/session.py`: 엔진, 세션, `get_db` 의존성. 연결마다 세션 시간대를 UTC로 고정한다.
  - 격리 수준은 READ COMMITTED다. REPEATABLE READ로 되돌리면 예약 중복 방지가 깨진다(docs/troubleshooting.md).
- `app/core/time.py`: UTC/KST 변환. 입력은 시간대 있는 시각만 받고(`AwareDatetime`), 응답은 `KstDatetime`으로 한국 시간을 내보낸다.
- `app/db/base.py`: `Base`(제약 이름 규칙 포함), `TimestampMixin`
- `app/models/`: ORM 모델. 새 모델은 `app/models/__init__.py`에도 import해야 Alembic이 인식한다.
- `migrations/`: Alembic. 접속 정보는 `alembic.ini`가 아니라 `.env`에서 읽는다(`migrations/env.py`).
  `alembic.ini`는 ASCII만 쓴다. Windows에서 cp949로 읽혀 한글이 들어가면 깨진다.
- `docs/erd.md`: DB 설계 문서. 스키마를 바꾸면 함께 갱신한다.
- 계층: `app/api/`(라우터, 입력과 응답 형식만) → `app/services/`(비즈니스 로직) → `app/models/`
  - 서비스는 `HTTPException` 대신 `app/core/exceptions.py`의 `NotFoundError`, `ConflictError` 등을 던진다. HTTP 상태 코드 변환은 예외 핸들러가 한다.
  - UNIQUE 같은 DB 제약 위반은 미리 SELECT로 확인하지 말고, 커밋할 때 `IntegrityError`를 잡아 변환한다(`app/db/errors.py`). 동시 요청에도 안전하기 때문이다.
- 인증: `app/core/security.py`(Argon2id 해시, JWT), `app/api/deps.py`(`CurrentUser`, `AdminUser` 의존성).
  - 로그인이 필요한 엔드포인트는 `user: CurrentUser`, 관리자 전용은 `_admin: AdminUser` 인자를 추가한다.
  - 관리자 계정은 `python -m app.cli create-admin`으로만 만든다. 가입 API는 항상 USER다.
  - `JWT_SECRET_KEY`는 기본값이 없다. `.env`에 없으면 앱이 시작되지 않는다(테스트는 conftest가 고정 키를 넣는다).
- `app/schemas/`: Pydantic 요청과 응답. 요청 모델은 `extra="forbid"`. PATCH 모델은 "안 보냄"과 "null"을 구분한다.
- `tests/`: pytest. 실제 MySQL 테스트 DB(`reservation_test`, `TEST_DB_NAME`으로 변경 가능)에서 돈다.
  - `conftest.py`가 세션 시작 시 `downgrade base` → `upgrade head`를 실행하고, 테스트마다 트랜잭션을 롤백한다(`join_transaction_mode="create_savepoint"`).
  - 이름이 `_test`로 끝나지 않는 DB에서는 테스트가 거부된다(개발 DB 보호).
  - 로그인 상태가 필요하면 `user`, `admin` 픽스처와 `auth_header(user)`를 쓴다(`tests/conftest.py`).
  - 동시성 테스트는 롤백 픽스처를 쓰지 않고 스레드마다 `SessionLocal()`로 실제 커밋한 뒤 직접 지운다(`tests/test_reservation_concurrency.py`). 실제 요청처럼 락 전에 사용자 조회를 먼저 한다.
  - CI는 MySQL 8.0 서비스 컨테이너를 띄운다(`.github/workflows/ci.yml`).
- `scripts/init_db.sql`: 로컬 DB와 앱 전용 사용자 생성 (root로 1회 실행). 테이블은 여기서 만들지 않고 Alembic으로 만든다.
- 시각은 모두 UTC, 시간대 정보 없는(naive) `datetime`으로 DB에 저장한다. 한국 시간 변환은 API 경계에서 한다.

## 규칙
- 비밀번호 같은 비밀 정보는 `.env`에만 둔다. 코드, 문서, 커밋에 넣지 않는다. 새 설정을 추가하면 `.env.example`도 함께 갱신한다.
- 의존성을 추가하면 버전을 고정해 `requirements.txt`(실행용) 또는 `requirements-dev.txt`(개발용)에 적는다.
- 커밋 메시지는 `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`, `chore: ...` 형식을 따르고, 내용은 한국어로 쓴다.
