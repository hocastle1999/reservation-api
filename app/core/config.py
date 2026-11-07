from functools import lru_cache

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
