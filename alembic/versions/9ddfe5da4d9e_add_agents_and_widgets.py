"""add_agents_and_widgets

Revision ID: 9ddfe5da4d9e
Revises: 8a8458bbfb06
Create Date: 2026-04-03 12:12:35

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ddfe5da4d9e'
down_revision: Union[str, None] = '8a8458bbfb06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create agents table
    op.create_table(
        'agents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Create agent_knowledge_bases junction table
    op.create_table(
        'agent_knowledge_bases',
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('knowledge_base_id', sa.Uuid(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('agent_id', 'knowledge_base_id')
    )

    # 3. Create widgets table
    op.create_table(
        'widgets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('theme', sa.JSON(), nullable=True),
        sa.Column('position', sa.String(length=50), server_default='bottom-right', nullable=False),
        sa.Column('greeting', sa.String(length=500), nullable=True),
        sa.Column('brand_color', sa.String(length=20), nullable=True),
        sa.Column('avatar_url', sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_id')
    )


def downgrade() -> None:
    op.drop_table('widgets')
    op.drop_table('agent_knowledge_bases')
    op.drop_table('agents')
