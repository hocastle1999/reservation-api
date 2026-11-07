from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.db.errors import is_duplicate_entry
from app.models import User, UserRole
from app.schemas.user import SignupRequest

INVALID_CREDENTIALS_MESSAGE = "이메일 또는 비밀번호가 올바르지 않습니다."


def signup(db: Session, data: SignupRequest, *, role: UserRole = UserRole.USER) -> User:
    """회원을 만든다. API로 가입하면 항상 USER이고, ADMIN은 관리 명령(app.cli)으로만 만든다."""
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role=role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if is_duplicate_entry(exc):
            raise ConflictError("이미 가입된 이메일입니다.") from exc
        raise
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))

    if user is None:
        # 없는 이메일이어도 해시 검증을 똑같이 한 번 실행한다.
        # 그러지 않으면 "없는 이메일"은 바로 응답하고 "비밀번호 틀림"은 해시 계산 시간만큼
        # 늦게 응답해서, 응답 시간으로 가입된 이메일인지 알아낼 수 있다. (타이밍 공격)
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise UnauthorizedError(INVALID_CREDENTIALS_MESSAGE)

    if not verify_password(password, user.password_hash):
        # 메시지도 위와 같게 한다. "없는 이메일입니다"라고 알려 주면 가입 여부가 드러난다.
        raise UnauthorizedError(INVALID_CREDENTIALS_MESSAGE)

    return user
