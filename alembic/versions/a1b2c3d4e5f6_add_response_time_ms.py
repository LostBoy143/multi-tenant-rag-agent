"""add response_time_ms to messages

Revision ID: a1b2c3d4e5f6
Revises: 681ecf56d28e
Create Date: 2026-04-10 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '681ecf56d28e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('response_time_ms', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'response_time_ms')
