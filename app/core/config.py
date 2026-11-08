from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """환경 변수(.env)에서 읽어 오는 설정값."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "reservation"
    db_user: str = "reservation_app"
    db_password: str = ""
    # DB 서버의 CA 인증서 파일 경로. 지정하면 SSL로 접속하고 서버 인증서를 검증한다.
    # 로컬 MySQL은 비워 두고, 인터넷을 거쳐 접속하는 관리형 DB(Aiven 등)에서 쓴다.
    # 검증 없이 암호화만 하면 중간에서 가짜 서버가 끼어들어도 알 수 없으므로, 반드시 검증한다.
    # (PyMySQL은 이 값이 없어도 서버가 지원하면 암호화하지만, 인증서는 검증하지 않는다)
    db_ssl_ca: str | None = None
    # 인증서의 호스트 이름이 DB_HOST와 맞는지도 확인한다.
    # 끄면 "믿을 수 있는 CA가 서명했는가"만 본다.
    db_ssl_verify_identity: bool = True

    # JWT 서명 키. 기본값을 두지 않는다: 설정을 빠뜨리면 약한 키로 조용히 도는 대신
    # 앱이 시작부터 실패하게 해서 바로 알아차리게 한다.
    # SecretStr: 로그나 오류 메시지에 값이 찍혀도 '**********'로 가려진다.
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # 겹치는 예약을 막는 방식. 두 방식을 비교하려고 둘 다 구현했다. (docs/erd.md)
    # lock: 자원 행을 SELECT ... FOR UPDATE로 잠근 뒤 겹침 검사
    # slot: 30분 칸 테이블(reservation_slots)에 넣고 기본키 중복으로 막음
    # 운영 중에 lock → slot으로 바꾸려면 기존 확정 예약의 칸을 먼저 채워 넣어야 한다.
    reservation_strategy: Literal["lock", "slot"] = "lock"

    @property
    def database_url(self) -> URL:
        # 문자열을 직접 이어 붙이지 않고 URL.create를 쓰는 이유:
        # 비밀번호에 @, :, / 같은 특수문자가 있어도 자동으로 올바르게 처리된다.
        return URL.create(
            drivername="mysql+pymysql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )

    @property
    def database_connect_args(self) -> dict[str, object]:
        """DB 연결마다 PyMySQL에 넘길 옵션. 앱(app/db/session.py)과 Alembic(migrations/env.py)이
        같은 값을 쓴다. 한쪽만 바꾸면 마이그레이션과 앱이 다른 조건으로 접속하게 된다.
        """
        # 연결마다 세션 시간대를 UTC로 고정한다. (docs/troubleshooting.md 참고)
        args: dict[str, object] = {"init_command": "SET time_zone = '+00:00'"}
        if self.db_ssl_ca:
            args |= {
                "ssl_ca": self.db_ssl_ca,
                "ssl_verify_cert": True,
                "ssl_verify_identity": self.db_ssl_verify_identity,
            }
        return args


@lru_cache
def get_settings() -> Settings:
    return Settings()
