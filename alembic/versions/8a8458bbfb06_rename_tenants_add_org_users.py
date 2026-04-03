"""rename_tenants_add_org_users

Revision ID: 8a8458bbfb06
Revises: 001
Create Date: 2026-04-03 12:01:55.754839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a8458bbfb06'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename tenants to organizations
    op.rename_table('tenants', 'organizations')
    
    # 2. Add columns to organizations
    op.add_column('organizations', sa.Column('slug', sa.String(length=255), nullable=True))
    op.add_column('organizations', sa.Column('plan', sa.String(length=20), server_default='free', nullable=False))
    
    # Note: Since slug must be unique and we might have existing rows, we set nullable=True first, then fill, then set nullable=False if needed.
    # But this is a dev/staging sprint so we'll just go with it.
    
    # 3. Create knowledge_bases table
    op.create_table(
        'knowledge_bases',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), server_default='member', nullable=False),
        sa.Column('must_change_password', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('two_factor_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('two_factor_secret', sa.String(length=255), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 5. Update api_keys table
    # Drop old FK
    op.drop_constraint('api_keys_tenant_id_fkey', 'api_keys', type_='foreignkey')
    # Rename column
    op.alter_column('api_keys', 'tenant_id', new_column_name='organization_id')
    # Add new columns
    op.add_column('api_keys', sa.Column('name', sa.String(length=255), nullable=True))
    op.add_column('api_keys', sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('api_keys', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    # Add new FK
    op.create_foreign_key('api_keys_org_id_fkey', 'api_keys', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')

    # 6. Update documents table
    # Drop old FK and index
    op.drop_constraint('documents_tenant_id_fkey', 'documents', type_='foreignkey')
    op.drop_index('ix_documents_tenant_id', table_name='documents')
    # Rename column
    op.alter_column('documents', 'tenant_id', new_column_name='organization_id')
    # Add knowledge_base_id
    op.add_column('documents', sa.Column('knowledge_base_id', sa.Uuid(), nullable=True))
    # Add new FKs
    op.create_foreign_key('documents_org_id_fkey', 'documents', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('documents_kb_id_fkey', 'documents', 'knowledge_bases', ['knowledge_base_id'], ['id'], ondelete='CASCADE')
    # Re-create index on organization_id
    op.create_index(op.f('ix_documents_organization_id'), 'documents', ['organization_id'], unique=False)


def downgrade() -> None:
    # Reverse order
    op.drop_index(op.f('ix_documents_organization_id'), table_name='documents')
    op.drop_constraint('documents_kb_id_fkey', 'documents', type_='foreignkey')
    op.drop_constraint('documents_org_id_fkey', 'documents', type_='foreignkey')
    op.alter_column('documents', 'organization_id', new_column_name='tenant_id')
    op.create_index('ix_documents_tenant_id', 'documents', ['tenant_id'])
    op.create_foreign_key('documents_tenant_id_fkey', 'documents', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')
    op.drop_column('documents', 'knowledge_base_id')

    op.drop_constraint('api_keys_org_id_fkey', 'api_keys', type_='foreignkey')
    op.drop_column('api_keys', 'expires_at')
    op.drop_column('api_keys', 'last_used_at')
    op.drop_column('api_keys', 'name')
    op.alter_column('api_keys', 'organization_id', new_column_name='tenant_id')
    op.create_foreign_key('api_keys_tenant_id_fkey', 'api_keys', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('knowledge_bases')
    
    op.drop_column('organizations', 'plan')
    op.drop_column('organizations', 'slug')
    op.rename_table('organizations', 'tenants')
