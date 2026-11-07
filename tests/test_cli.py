from sqlalchemy import select

from app import cli
from app.models import User, UserRole


def run_create_admin(monkeypatch, db_session, passwords):
    answers = iter(passwords)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    monkeypatch.setattr(cli, "SessionLocal", lambda: db_session)
    return cli.create_admin("Boss@Example.com", "관리자")


def test_create_admin_creates_admin_user(monkeypatch, db_session, capsys):
    code = run_create_admin(monkeypatch, db_session, ["admin-password", "admin-password"])

    assert code == 0
    saved = db_session.scalar(select(User).where(User.email == "boss@example.com"))
    assert saved.role is UserRole.ADMIN
    assert "관리자 계정을 만들었습니다" in capsys.readouterr().out


def test_create_admin_rejects_mismatched_confirmation(monkeypatch, db_session):
    code = run_create_admin(monkeypatch, db_session, ["admin-password", "different-pw"])

    assert code == 1
    assert db_session.scalar(select(User).where(User.email == "boss@example.com")) is None


def test_create_admin_rejects_short_password(monkeypatch, db_session):
    assert run_create_admin(monkeypatch, db_session, ["short", "short"]) == 1
