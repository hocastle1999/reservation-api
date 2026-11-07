from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.core.security import create_access_token
from app.schemas.user import SignupRequest, TokenResponse, UserRead
from app.services import auth_service

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/signup",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "이미 가입된 이메일"}},
    summary="회원가입",
)
def signup(data: SignupRequest, db: DbSession):
    return auth_service.signup(db, data)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    responses={401: {"description": "이메일 또는 비밀번호가 틀림"}},
    summary="로그인 (액세스 토큰 발급)",
    description=(
        "OAuth2 규격에 맞춰 form 데이터로 받는다. `username` 칸에 이메일을 넣는다. "
        "그래서 Swagger UI의 Authorize 버튼으로 바로 로그인할 수 있다."
    ),
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    user = auth_service.authenticate(db, form.username, form.password)
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/users/me", response_model=UserRead, summary="내 정보")
def read_me(user: CurrentUser):
    return user
