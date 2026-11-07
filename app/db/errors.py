from sqlalchemy.exc import IntegrityError

# MySQL 오류 번호 1062: Duplicate entry (UNIQUE 제약 위반)
MYSQL_DUPLICATE_ENTRY = 1062


def is_duplicate_entry(exc: IntegrityError) -> bool:
    """IntegrityError가 UNIQUE 제약 위반인지 확인한다. (외래키, CHECK 위반과 구분)"""
    args = getattr(exc.orig, "args", ())
    return bool(args) and args[0] == MYSQL_DUPLICATE_ENTRY
