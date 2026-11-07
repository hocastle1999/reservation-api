from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import User
from tests.conftest import TEST_PASSWORD, auth_header


def signup(client, **overrides):
    body = {"email": "new@example.com", "password": "long-enough-pw", "name": "새 회원"} | overrides
    return client.post("/auth/signup", json=body)


def login(client, email, password):
    # OAuth2 규격: JSON이 아니라 form 데이터, 이메일은 username 칸에 넣는다.
    return client.post("/auth/login", data={"username": email, "password": password})


# --- 회원가입 -----------------------------------------------------------------


def test_signup_creates_user_with_user_role(client, db_session):
    response = signup(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "USER"
    assert "password" not in body and "password_hash" not in body

    saved = db_session.scalar(select(User).where(User.email == "new@example.com"))
    # 비밀번호 원문이 아니라 Argon2id 해시로 저장된다.
    assert saved.password_hash != "long-enough-pw"
    assert saved.password_hash.startswith("$argon2id$")


def test_signup_normalizes_email_to_lowercase(client):
    response = signup(client, email="New.User@Example.COM")

    assert response.json()["email"] == "new.user@example.com"


def test_signup_ignores_role_in_request(client):
    # 가입 요청으로 관리자가 될 수 없다. (extra="forbid"라 422)
    assert signup(client, role="ADMIN").status_code == 422


def test_signup_with_existing_email_returns_409(client, user):
    response = signup(client, email="USER@example.com")

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 가입된 이메일입니다."}


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"password": "x" * 129},
        {"name": "  "},
    ],
    ids=["bad-email", "short-password", "long-password", "blank-name"],
)
def test_signup_with_invalid_body_returns_422(client, overrides):
    assert signup(client, **overrides).status_code == 422


# --- 로그인 -------------------------------------------------------------------


def test_login_returns_token_that_identifies_user(client, user):
    response = login(client, "user@example.com", TEST_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"

    me = client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_login_email_is_case_insensitive(client, user):
    assert login(client, "User@Example.com", TEST_PASSWORD).status_code == 200


def test_login_with_wrong_password_and_unknown_email_look_the_same(client, user):
    wrong_password = login(client, "user@example.com", "wrong-password")
    unknown_email = login(client, "nobody@example.com", TEST_PASSWORD)

    # 응답만 보고는 가입된 이메일인지 알 수 없어야 한다.
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.headers["WWW-Authenticate"] == "Bearer"


# --- 토큰 검증 -----------------------------------------------------------------


def test_me_without_token_returns_401(client):
    response = client.get("/users/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "로그인이 필요합니다."}


def _token(user_id, *, key=None, expires_delta=timedelta(minutes=5), algorithm="HS256"):
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + expires_delta}
    secret = key or settings.jwt_secret_key.get_secret_value()
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.mark.parametrize(
    "make_token",
    [
        lambda uid: _token(uid, expires_delta=timedelta(seconds=-1)),
        lambda uid: _token(uid, key="another-secret-key-that-is-also-long-enough-0123"),
        lambda uid: _token(uid, algorithm="HS512"),
        lambda uid: "not.a.jwt",
        lambda uid: _token(999_999),
    ],
    ids=["expired", "wrong-signature", "unexpected-algorithm", "garbage", "deleted-user"],
)
def test_me_with_invalid_token_returns_401(client, user, make_token):
    token = make_token(user.id)

    response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


# --- 권한 (자원 API) -------------------------------------------------------------


def test_anyone_can_list_resources(client):
    assert client.get("/resources").status_code == 200


def test_create_resource_requires_login(client):
    response = client.post("/resources", json={"name": "A", "capacity": 2})

    assert response.status_code == 401


def test_create_resource_forbidden_for_normal_user(client, user):
    response = client.post(
        "/resources", json={"name": "A", "capacity": 2}, headers=auth_header(user)
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "관리자만 사용할 수 있습니다."}


def test_admin_can_create_and_update_resource(client, admin):
    headers = auth_header(admin)

    created = client.post("/resources", json={"name": "A", "capacity": 2}, headers=headers)
    updated = client.patch(
        f"/resources/{created.json()['id']}", json={"capacity": 3}, headers=headers
    )

    assert created.status_code == 201
    assert updated.status_code == 200


def test_update_resource_forbidden_for_normal_user(client, user, admin):
    resource_id = client.post(
        "/resources", json={"name": "A", "capacity": 2}, headers=auth_header(admin)
    ).json()["id"]

    response = client.patch(
        f"/resources/{resource_id}", json={"capacity": 9}, headers=auth_header(user)
    )

    assert response.status_code == 403
