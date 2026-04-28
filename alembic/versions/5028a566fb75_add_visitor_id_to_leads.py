"""add_visitor_id_to_leads

Revision ID: 5028a566fb75
Revises: b3c4d5e6f7a8
Create Date: 2026-04-28 17:06:29.112551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5028a566fb75'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('visitor_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_leads_visitor_id'), 'leads', ['visitor_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_leads_visitor_id'), table_name='leads')
    op.drop_column('leads', 'visitor_id')
