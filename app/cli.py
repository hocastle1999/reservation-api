"""관리 명령.

관리자 계정 만들기:
    .\\.venv\\Scripts\\python.exe -m app.cli create-admin --email admin@example.com --name 관리자

비밀번호는 명령줄 인자로 받지 않고 입력 프롬프트로 받는다.
(명령줄 인자는 셸 기록과 프로세스 목록에 그대로 남기 때문이다.)
"""

import argparse
import getpass
import sys

from pydantic import ValidationError

from app.core.exceptions import ConflictError
from app.db.session import SessionLocal
from app.models import UserRole
from app.schemas.user import SignupRequest
from app.services import auth_service


def create_admin(email: str, name: str) -> int:
    password = getpass.getpass("비밀번호: ")
    if password != getpass.getpass("비밀번호 확인: "):
        print("비밀번호가 서로 다릅니다.", file=sys.stderr)
        return 1

    try:
        data = SignupRequest(email=email, password=password, name=name)
    except ValidationError as exc:
        print(f"입력값이 올바르지 않습니다:\n{exc}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            user = auth_service.signup(db, data, role=UserRole.ADMIN)
        except ConflictError as exc:
            print(exc.detail, file=sys.stderr)
            return 1
    print(f"관리자 계정을 만들었습니다: id={user.id}, email={user.email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="관리자 계정 만들기")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)

    args = parser.parse_args()
    if args.command == "create-admin":
        return create_admin(args.email, args.name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
