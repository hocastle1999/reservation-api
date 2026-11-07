from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, StringConstraints

from app.models import UserRole


def _lowercase(value: str) -> str:
    return value.lower()


# 이메일은 소문자로 바꿔 저장한다. DB 콜레이션이 대소문자를 구분하지 않아 중복은 막히지만,
# 저장된 값의 모양을 하나로 맞춰 두면 비교, 검색, 화면 표시가 단순해진다.
Email = Annotated[EmailStr, AfterValidator(_lowercase)]
# 길이 제한만 둔다. (NIST SP 800-63B: 복잡도 규칙보다 길이가 중요, 최소 8자 권장)
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
UserName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: Password
    name: UserName


class UserRead(BaseModel):
    """응답용. password_hash는 절대 포함하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: UserRole


class TokenResponse(BaseModel):
    # OAuth2 규격의 필드 이름. Swagger UI의 Authorize 버튼이 이 형식을 기대한다.
    access_token: str
    token_type: str = "bearer"
