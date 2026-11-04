"""line item evidence and corrections

Revision ID: ce55760f6cb5
Revises: b1a2c3d4e5f6
Create Date: 2026-11-04 23:47:01.297687

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'ce55760f6cb5'
down_revision: str | None = 'b1a2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('correction', sa.Column('line_item_id', sa.String(length=36), nullable=True))
    op.alter_column('correction', 'field_id',
               existing_type=sa.VARCHAR(length=36),
               nullable=True)
    op.create_index(op.f('ix_correction_line_item_id'), 'correction', ['line_item_id'], unique=False)
    op.create_foreign_key(
        'fk_correction_line_item', 'correction', 'line_item',
        ['line_item_id'], ['id'], ondelete='CASCADE',
    )
    op.create_check_constraint(
        'ck_correction_single_target',
        'correction',
        '(field_id IS NOT NULL) <> (line_item_id IS NOT NULL)',
    )

    op.add_column(
        'line_item',
        sa.Column(
            'status',
            sa.Enum('SUGGESTED', 'CONFIRMED', 'CORRECTED', name='fieldstatus',
                    native_enum=False, length=32),
            nullable=False,
            server_default='SUGGESTED',
        ),
    )
    op.add_column(
        'line_item',
        sa.Column(
            'verification_level',
            sa.Enum('EXACT', 'CONTAINED', 'CLAIMED', 'NONE', name='evidencelevel',
                    native_enum=False, length=32),
            nullable=False,
            server_default='NONE',
        ),
    )
    op.add_column('line_item', sa.Column('effective_conf', sa.Float(), nullable=False, server_default='0'))
    op.add_column('line_item', sa.Column('page_idx', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('line_item', sa.Column('bbox', sa.JSON(), nullable=True))
    op.add_column('line_item', sa.Column('quote', sa.Text(), nullable=True))
    op.add_column('line_item', sa.Column('updated_by', sa.String(length=36), nullable=True))
    op.add_column(
        'line_item',
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_foreign_key(
        'fk_line_item_updated_by', 'line_item', 'user', ['updated_by'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_line_item_updated_by', 'line_item', type_='foreignkey')
    op.drop_column('line_item', 'updated_at')
    op.drop_column('line_item', 'updated_by')
    op.drop_column('line_item', 'quote')
    op.drop_column('line_item', 'bbox')
    op.drop_column('line_item', 'page_idx')
    op.drop_column('line_item', 'effective_conf')
    op.drop_column('line_item', 'verification_level')
    op.drop_column('line_item', 'status')

    op.drop_constraint('ck_correction_single_target', 'correction', type_='check')
    op.drop_constraint('fk_correction_line_item', 'correction', type_='foreignkey')
    op.drop_index(op.f('ix_correction_line_item_id'), table_name='correction')
    op.alter_column('correction', 'field_id',
               existing_type=sa.VARCHAR(length=36),
               nullable=False)
    op.drop_column('correction', 'line_item_id')
