"""add reservation_slots

Revision ID: dd48e758a4c9
Revises: 932fa674f0d2
Create Date: 2026-11-08 09:24:32.358163

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd48e758a4c9"
down_revision: str | Sequence[str] | None = "932fa674f0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """방법 B(시간 칸 + UNIQUE)용 테이블. 기본키 (resource_id, slot_start)가 중복 예약을 막는다."""
    op.create_table(
        "reservation_slots",
        sa.Column("resource_id", sa.BigInteger(), nullable=False),
        sa.Column("slot_start", sa.DateTime(), nullable=False),
        sa.Column("reservation_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name=op.f("fk_reservation_slots_reservation_id_reservations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_reservation_slots_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("resource_id", "slot_start", name=op.f("pk_reservation_slots")),
    )
    op.create_index(
        "ix_reservation_slots_reservation_id", "reservation_slots", ["reservation_id"], unique=False
    )


def downgrade() -> None:
    # 인덱스를 먼저 지우지 않는다. ix_reservation_slots_reservation_id는 reservation_id 외래키가
    # 쓰는 유일한 인덱스라, 테이블보다 먼저 지우면 MySQL 오류 1553이 난다.
    # 테이블을 지우면 인덱스도 함께 사라진다. (docs/troubleshooting.md 2026-11-07 항목)
    op.drop_table("reservation_slots")
