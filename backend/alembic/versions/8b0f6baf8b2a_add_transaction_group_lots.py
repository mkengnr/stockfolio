"""add transaction group lots

Revision ID: 8b0f6baf8b2a
Revises: 1ea62c42a6ce
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8b0f6baf8b2a'
down_revision: Union[str, None] = '1ea62c42a6ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('requires_review', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        'source_groups',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=7), server_default='#6366f1', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('share_token', sa.String(length=36), nullable=True),
        sa.Column('share_requires_auth', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_source_groups_share_token'), 'source_groups', ['share_token'], unique=True)
    op.create_index(op.f('ix_source_groups_user_id'), 'source_groups', ['user_id'], unique=False)
    op.add_column('transactions', sa.Column('source_group_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_transactions_source_group_id_source_groups',
        'transactions',
        'source_groups',
        ['source_group_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_index(op.f('ix_transactions_source_group_id'), 'transactions', ['source_group_id'], unique=False)

    op.create_table(
        'rollup_groups',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=7), server_default='#6366f1', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('share_token', sa.String(length=36), nullable=True),
        sa.Column('share_requires_auth', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_rollup_groups_share_token'), 'rollup_groups', ['share_token'], unique=True)
    op.create_index(op.f('ix_rollup_groups_user_id'), 'rollup_groups', ['user_id'], unique=False)

    op.create_table(
        'labels',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=7), server_default='#6366f1', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('share_token', sa.String(length=36), nullable=True),
        sa.Column('share_requires_auth', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_labels_share_token'), 'labels', ['share_token'], unique=True)
    op.create_index(op.f('ix_labels_user_id'), 'labels', ['user_id'], unique=False)

    op.create_table(
        'rollup_group_members',
        sa.Column('rollup_group_id', sa.Uuid(), nullable=False),
        sa.Column('source_group_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['rollup_group_id'], ['rollup_groups.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_group_id'], ['source_groups.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('rollup_group_id', 'source_group_id'),
    )
    op.create_index(
        op.f('ix_rollup_group_members_source_group_id'),
        'rollup_group_members',
        ['source_group_id'],
        unique=False,
    )

    op.create_table(
        'buy_lots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('transaction_id', sa.Uuid(), nullable=False),
        sa.Column('holding_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('source_group_id', sa.Uuid(), nullable=True),
        sa.Column('original_quantity', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('remaining_quantity', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('original_quantity > 0'),
        sa.CheckConstraint('remaining_quantity >= 0'),
        sa.CheckConstraint('remaining_quantity <= original_quantity'),
        sa.CheckConstraint('unit_price > 0'),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_group_id'], ['source_groups.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id'),
    )
    op.create_index(op.f('ix_buy_lots_holding_id'), 'buy_lots', ['holding_id'], unique=False)
    op.create_index(op.f('ix_buy_lots_source_group_id'), 'buy_lots', ['source_group_id'], unique=False)
    op.create_index(op.f('ix_buy_lots_user_id'), 'buy_lots', ['user_id'], unique=False)

    op.create_table(
        'sell_lot_allocations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('sell_transaction_id', sa.Uuid(), nullable=False),
        sa.Column('buy_lot_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('quantity > 0'),
        sa.ForeignKeyConstraint(['buy_lot_id'], ['buy_lots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sell_transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sell_transaction_id', 'buy_lot_id'),
    )
    op.create_index(op.f('ix_sell_lot_allocations_buy_lot_id'), 'sell_lot_allocations', ['buy_lot_id'], unique=False)
    op.create_index(
        op.f('ix_sell_lot_allocations_sell_transaction_id'),
        'sell_lot_allocations',
        ['sell_transaction_id'],
        unique=False,
    )

    op.create_table(
        'transaction_labels',
        sa.Column('transaction_id', sa.Uuid(), nullable=False),
        sa.Column('label_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('transaction_id', 'label_id'),
    )
    op.create_index(op.f('ix_transaction_labels_label_id'), 'transaction_labels', ['label_id'], unique=False)

    op.execute(
        sa.text(
            """
            INSERT INTO source_groups (
                id, user_id, name, color, description, share_token,
                share_requires_auth, created_at, updated_at
            )
            SELECT
                id, user_id, name, color, description, share_token,
                share_requires_auth, created_at, updated_at
            FROM tags
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH legacy_holding_tag_counts AS (
                SELECT
                    holding_tags.holding_id,
                    COUNT(*) AS tag_count,
                    BOOL_AND(tags.user_id = holdings.user_id) AS owners_match,
                    (array_agg(holding_tags.tag_id))[1] AS tag_id
                FROM holding_tags
                JOIN holdings ON holdings.id = holding_tags.holding_id
                JOIN tags ON tags.id = holding_tags.tag_id
                GROUP BY holding_tags.holding_id
            )
            UPDATE transactions AS legacy_transactions
            SET source_group_id = CASE WHEN legacy_tags.tag_count = 1 AND legacy_tags.owners_match THEN legacy_tags.tag_id ELSE NULL END
            FROM legacy_holding_tag_counts AS legacy_tags
            WHERE legacy_tags.holding_id = legacy_transactions.holding_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO buy_lots (
                id, transaction_id, holding_id, user_id, source_group_id,
                original_quantity, remaining_quantity, unit_price,
                created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                transactions.id,
                transactions.holding_id,
                transactions.user_id,
                transactions.source_group_id,
                transactions.quantity,
                transactions.quantity,
                transactions.price,
                transactions.created_at,
                transactions.created_at
            FROM transactions
            WHERE transactions.type = 'BUY'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE transactions
            SET requires_review = true
            WHERE type = 'SELL'
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_transaction_labels_label_id'), table_name='transaction_labels')
    op.drop_table('transaction_labels')
    op.drop_index(op.f('ix_sell_lot_allocations_sell_transaction_id'), table_name='sell_lot_allocations')
    op.drop_index(op.f('ix_sell_lot_allocations_buy_lot_id'), table_name='sell_lot_allocations')
    op.drop_table('sell_lot_allocations')
    op.drop_index(op.f('ix_buy_lots_user_id'), table_name='buy_lots')
    op.drop_index(op.f('ix_buy_lots_source_group_id'), table_name='buy_lots')
    op.drop_index(op.f('ix_buy_lots_holding_id'), table_name='buy_lots')
    op.drop_table('buy_lots')
    op.drop_index(op.f('ix_rollup_group_members_source_group_id'), table_name='rollup_group_members')
    op.drop_table('rollup_group_members')
    op.drop_index(op.f('ix_labels_user_id'), table_name='labels')
    op.drop_index(op.f('ix_labels_share_token'), table_name='labels')
    op.drop_table('labels')
    op.drop_index(op.f('ix_rollup_groups_user_id'), table_name='rollup_groups')
    op.drop_index(op.f('ix_rollup_groups_share_token'), table_name='rollup_groups')
    op.drop_table('rollup_groups')
    op.drop_index(op.f('ix_transactions_source_group_id'), table_name='transactions')
    op.drop_constraint('fk_transactions_source_group_id_source_groups', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'source_group_id')
    op.drop_index(op.f('ix_source_groups_user_id'), table_name='source_groups')
    op.drop_index(op.f('ix_source_groups_share_token'), table_name='source_groups')
    op.drop_table('source_groups')
    op.drop_column('transactions', 'requires_review')
