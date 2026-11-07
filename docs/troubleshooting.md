# 문제 해결 기록

개발 중 겪은 문제를 아래 형식으로 쌓아 둡니다. 최신 항목을 위에 추가합니다.

<!--
## YYYY-MM-DD 제목 (한 줄로 증상 요약)

**문제**: 어떤 상황에서 무엇이 잘못됐는지 (에러 메시지, 재현 방법)

**원인**: 왜 그런 일이 생겼는지. 어떻게 원인을 찾았는지도 적는다.

**해결**: 무엇을 바꿨는지 (관련 커밋 링크)

**배운 점**: 다음에 같은 문제를 어떻게 피할지, 무엇을 새로 알게 됐는지
-->

## 2026-11-07 Alembic 되돌리기(downgrade)가 MySQL 오류 1553으로 실패

**문제**: 첫 마이그레이션을 `alembic downgrade base`로 되돌리자 아래 오류가 났다.

```
pymysql.err.OperationalError: (1553, "Cannot drop index 'ix_reservations_user_start':
needed in a foreign key constraint")
```

**원인**: Alembic이 자동 생성한 `downgrade()`는 "인덱스 삭제 → 테이블 삭제" 순서였다.

- `reservations.user_id`의 외래키는 `(user_id, start_at)` 복합 인덱스를 써서 검사를 한다. InnoDB는 외래키 컬럼에 인덱스가 반드시 있어야 하기 때문이다.
- 외래키를 만들 때 MySQL이 자동으로 만든 인덱스는, 복합 인덱스가 생기면서 지워졌다. 그래서 이 복합 인덱스가 외래키를 받치는 유일한 인덱스가 되었다.
- 외래키가 살아 있는 상태에서 그 인덱스만 지우려고 하니 MySQL이 거부했다.

**해결**: `downgrade()`에서 인덱스 삭제를 빼고 테이블만 지우도록 고쳤다. 테이블을 지우면 인덱스도 함께 사라진다. 그다음 `downgrade base → upgrade head`를 다시 실행해 왕복이 되는 것을 확인했다.

**배운 점**:

- 자동 생성된 마이그레이션은 그대로 믿지 말고 읽어 본 뒤, 올리기와 되돌리기를 둘 다 실제로 실행해 본다.
- 나중에 인덱스를 바꿀 때도 같은 문제가 생긴다. 외래키 컬럼이 앞에 오는 인덱스를 지우려면 새 인덱스를 먼저 만들고 옛 인덱스를 지워야 한다. 아니면 외래키를 잠시 지웠다가 다시 만든다.

## 2026-11-07 DB 기본값 CURRENT_TIMESTAMP가 한국 시간으로 저장될 뻔함

**문제**: 시각은 UTC로 저장하기로 설계했다. 그런데 `created_at`의 기본값인 `CURRENT_TIMESTAMP`는 DB 세션의 시간대를 따른다. 로컬 MySQL의 전역 시간대를 확인해 보니 `SYSTEM`, 즉 PC 시간대(KST)였다.

**원인**: `DATETIME` 컬럼은 시간대 정보 없이 값만 저장한다. 그래서 세션 시간대가 KST이면 KST 시각이 그대로 들어간다. 이렇게 되면 앱이 넣는 `start_at`(UTC)과 DB가 넣는 `created_at`(KST)의 기준이 9시간 어긋난다.

**해결**: 앱과 Alembic의 DB 연결마다 `SET time_zone = '+00:00'`을 실행하도록 했다. PyMySQL의 `init_command` 옵션을 썼다(`app/db/session.py`, `migrations/env.py`). 확인해 보니 세션 시간대는 `+00:00`이었고, 방금 넣은 행의 `created_at`과 UTC 현재 시각의 차이는 0초였다.

**배운 점**: 서버 설정(전역 시간대)에 기대지 않고 연결 단위로 시간대를 고정하면, 로컬과 배포 환경의 DB 설정이 달라도 같은 결과가 나온다.

## 2026-11-07 Windows에서 alembic.ini에 한글 주석을 넣자 UnicodeDecodeError

**문제**: `alembic.ini`에 한글 주석을 추가한 뒤 `alembic revision`을 실행하자 아래 오류가 났다.

```
UnicodeDecodeError: 'cp949' codec can't decode byte 0xec in position 3563
```

**원인**: Alembic은 `alembic.ini`를 OS의 기본 인코딩(`encoding="locale"`)으로 읽는다. 한국어 Windows의 기본 인코딩은 cp949인데, 파일은 UTF-8로 저장되어 있었다. 오류 추적(traceback)의 `read_config_parser` 부분에서 원인을 찾았다.

**해결**: `alembic.ini`의 주석을 영어로 바꿔 ASCII 문자만 남겼다. 파일 안에도 그 이유를 주석으로 적어 두었다.

**배운 점**: Windows에서는 "파일을 어떤 인코딩으로 읽는가"가 도구마다 다르다. 설정 파일은 ASCII로 쓰는 게 가장 안전하다. 파이썬 코드에서 파일을 열 때는 `encoding="utf-8"`을 항상 명시한다.
