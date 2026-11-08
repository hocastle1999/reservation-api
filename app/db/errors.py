from sqlalchemy.exc import DBAPIError, IntegrityError

# MySQL 오류 번호 1062: Duplicate entry (UNIQUE 제약 위반)
MYSQL_DUPLICATE_ENTRY = 1062
# MySQL 오류 번호 1213: Deadlock found. InnoDB가 트랜잭션 하나를 골라 통째로 롤백했다.
MYSQL_DEADLOCK = 1213


def _mysql_error_code(exc: DBAPIError) -> int | None:
    args = getattr(exc.orig, "args", ())
    return args[0] if args else None


def is_duplicate_entry(exc: IntegrityError) -> bool:
    """IntegrityError가 UNIQUE 제약 위반인지 확인한다. (외래키, CHECK 위반과 구분)"""
    return _mysql_error_code(exc) == MYSQL_DUPLICATE_ENTRY


def is_deadlock(exc: DBAPIError) -> bool:
    return _mysql_error_code(exc) == MYSQL_DEADLOCK
