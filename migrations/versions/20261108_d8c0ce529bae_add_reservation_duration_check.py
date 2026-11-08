"""add reservation duration check

Revision ID: d8c0ce529bae
Revises: dd48e758a4c9
Create Date: 2026-11-08 09:45:03.589334

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8c0ce529bae"
down_revision: str | Sequence[str] | None = "dd48e758a4c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Alembic autogenerate는 CHECK 제약의 추가를 감지하지 못해서 직접 작성했다.
# 값은 app/models/reservation.py의 MAX_DURATION_HOURS(8시간)와 같아야 한다.
# 모델 상수를 import하지 않고 숫자를 적는 이유: 마이그레이션은 "그 시점의 스키마"를
# 기록한 것이라, 나중에 상수가 바뀌어도 이 파일의 결과는 바뀌면 안 된다.
CONSTRAINT_NAME = "ck_reservations_duration"


def upgrade() -> None:
    """예약 길이 상한(8시간)을 DB CHECK 제약으로 건다. 겹침 검사의 검색 범위 축소가 이에 기댄다."""
    op.create_check_constraint(
        op.f(CONSTRAINT_NAME),
        "reservations",
        "TIMESTAMPDIFF(MINUTE, start_at, end_at) <= 480",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT_NAME), "reservations", type_="check")
