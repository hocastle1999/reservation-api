from functools import lru_cache

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

    # JWT 서명 키. 기본값을 두지 않는다: 설정을 빠뜨리면 약한 키로 조용히 도는 대신
    # 앱이 시작부터 실패하게 해서 바로 알아차리게 한다.
    # SecretStr: 로그나 오류 메시지에 값이 찍혀도 '**********'로 가려진다.
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
