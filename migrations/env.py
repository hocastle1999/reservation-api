from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  모든 모델을 등록해야 autogenerate가 테이블을 본다
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 접속 정보는 alembic.ini가 아니라 .env에서 읽는다. (비밀번호를 git에 올리지 않기 위해)
database_url = get_settings().database_url


def run_migrations_offline() -> None:
    """DB에 접속하지 않고 SQL만 출력한다. (alembic upgrade head --sql)"""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """DB에 접속해 마이그레이션을 실제로 적용한다."""
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
        # 앱과 같은 세션 시간대(UTC)를 쓴다. (app/db/session.py 참고)
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
