"""여러 라우터에서 같이 쓰는 의존성 (DB 세션, 로그인한 사용자, 권한 검사)."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models import User, UserRole

DbSession = Annotated[Session, Depends(get_db)]

# Authorization: Bearer <토큰> 헤더에서 토큰을 꺼낸다.
# tokenUrl은 Swagger UI의 Authorize 버튼이 로그인할 주소다.
# auto_error=False: 헤더가 없을 때 FastAPI 기본 오류 대신 아래에서 같은 형식의 401을 낸다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(db: DbSession, token: Annotated[str | None, Depends(oauth2_scheme)]) -> User:
    if token is None:
        raise UnauthorizedError("로그인이 필요합니다.")
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError as exc:
        raise UnauthorizedError("인증 정보가 올바르지 않거나 만료되었습니다.") from exc

    # 토큰 안의 정보(역할 등)를 그대로 믿지 않고 매번 DB에서 사용자를 읽는다.
    # 그래야 탈퇴했거나 권한이 바뀐 사용자의 옛 토큰이 그대로 통하지 않는다.
    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("인증 정보가 올바르지 않거나 만료되었습니다.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise ForbiddenError("관리자만 사용할 수 있습니다.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
