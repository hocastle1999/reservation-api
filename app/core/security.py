from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

# 비밀번호 해시는 Argon2id를 쓴다.
# - SHA-256 같은 일반 해시는 너무 빨라서, DB가 유출되면 무차별 대입으로 금방 뚫린다.
# - Argon2id는 일부러 느리고 메모리를 많이 쓰게 만든 비밀번호 전용 알고리즘이다.
#   (2015년 Password Hashing Competition 우승, OWASP 1순위 권장)
# - 솔트(salt)는 해시마다 무작위로 만들어 결과 문자열 안에 함께 저장된다.
#   그래서 같은 비밀번호라도 해시값이 매번 다르다.
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# 없는 이메일로 로그인할 때도 해시 검증을 한 번 실행하기 위한 더미 해시. (아래 auth_service 참고)
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # JWT 표준상 sub는 문자열이어야 한다.
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> int:
    """토큰을 검증하고 사용자 ID를 돌려준다. 서명이 틀리거나 만료됐으면 InvalidTokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            # 허용할 알고리즘을 명시한다. 토큰 헤더의 alg를 그대로 믿으면
            # alg를 "none"으로 바꾼 위조 토큰 같은 공격에 당할 수 있다.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError from exc
