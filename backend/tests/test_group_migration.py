import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
import shutil
import subprocess
import uuid

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.database import Base
from app.models import (
    BuyLot,
    Holding,
    Label,
    RollupGroup,
    RollupGroupMember,
    SellLotAllocation,
    SourceGroup,
    Transaction,
    TransactionLabel,
    User,
)
from app.models.holding import Currency, Market, TransactionType


BACKEND_PATH = Path(__file__).parents[1]
MIGRATION_PATH = (
    BACKEND_PATH
    / "alembic"
    / "versions"
    / "8b0f6baf8b2a_add_transaction_group_lots.py"
)


def _relationship_names(model: type) -> set[str]:
    return set(sa.inspect(model).relationships.keys())


def _relationship(model: type, name: str):
    return sa.inspect(model).relationships[name]


@pytest.fixture
def isolated_postgresql_url(tmp_path: Path):
    pytest.importorskip("asyncpg")
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if initdb is None or pg_ctl is None:
        pytest.skip("isolated PostgreSQL test requires initdb and pg_ctl")

    data_path = tmp_path / "postgres"
    log_path = tmp_path / "postgres.log"
    socket_path = tmp_path / "socket"
    socket_path.mkdir()
    initdb_result = subprocess.run(
        [
            initdb,
            "-D",
            str(data_path),
            "--auth=trust",
            "--username=postgres",
            "--no-locale",
            "--encoding=UTF8",
        ],
        capture_output=True,
        text=True,
    )
    if initdb_result.returncode:
        pytest.skip("isolated PostgreSQL cluster unavailable in this environment")

    start_result = subprocess.run(
        [
            pg_ctl,
            "-D",
            str(data_path),
            "-l",
            str(log_path),
            "-o",
            f"-F -h '' -k {socket_path}",
            "-w",
            "start",
        ],
        capture_output=True,
        text=True,
    )
    if start_result.returncode:
        subprocess.run(
            [pg_ctl, "-D", str(data_path), "-m", "immediate", "-w", "stop"],
            capture_output=True,
            text=True,
        )
        pytest.skip("isolated PostgreSQL server unavailable in this environment")
    try:
        yield f"postgresql+asyncpg://postgres@/postgres?host={socket_path}"
    finally:
        subprocess.run(
            [pg_ctl, "-D", str(data_path), "-m", "immediate", "-w", "stop"],
            check=True,
            capture_output=True,
            text=True,
        )


async def _seed_delete_graph(engine, *, classifications: bool = True) -> dict[str, uuid.UUID]:
    ids = {
        name: uuid.uuid4()
        for name in (
            "user",
            "holding",
            "source_group",
            "rollup_group",
            "label",
            "buy_transaction",
            "sell_transaction",
            "buy_lot",
            "allocation",
        )
    }
    async with engine.begin() as connection:
        await connection.execute(
            User.__table__.insert().values(
                id=ids["user"],
                email=f"{ids['user']}@example.com",
                is_admin=False,
                is_active=True,
            )
        )
        await connection.execute(
            Holding.__table__.insert().values(
                id=ids["holding"],
                user_id=ids["user"],
                ticker="AAPL",
                market=Market.US,
                name="Apple",
                quantity=Decimal("1"),
                avg_price=Decimal("100"),
                currency=Currency.USD,
                first_buy_date=date(2026, 1, 1),
                is_active=True,
            )
        )
        if classifications:
            await connection.execute(
                SourceGroup.__table__.insert().values(
                    id=ids["source_group"],
                    user_id=ids["user"],
                    name="Brokerage",
                )
            )
            await connection.execute(
                RollupGroup.__table__.insert().values(
                    id=ids["rollup_group"],
                    user_id=ids["user"],
                    name="Retirement",
                )
            )
            await connection.execute(
                RollupGroupMember.__table__.insert().values(
                    rollup_group_id=ids["rollup_group"],
                    source_group_id=ids["source_group"],
                )
            )
            await connection.execute(
                Label.__table__.insert().values(
                    id=ids["label"],
                    user_id=ids["user"],
                    name="Long term",
                )
            )
        for transaction_id, transaction_type in (
            (ids["buy_transaction"], TransactionType.BUY),
            (ids["sell_transaction"], TransactionType.SELL),
        ):
            await connection.execute(
                Transaction.__table__.insert().values(
                    id=transaction_id,
                    holding_id=ids["holding"],
                    user_id=ids["user"],
                    source_group_id=ids["source_group"] if classifications else None,
                    type=transaction_type,
                    quantity=Decimal("1"),
                    price=Decimal("100"),
                    transaction_date=date(2026, 1, 1),
                )
            )
        await connection.execute(
            BuyLot.__table__.insert().values(
                id=ids["buy_lot"],
                transaction_id=ids["buy_transaction"],
                holding_id=ids["holding"],
                user_id=ids["user"],
                source_group_id=ids["source_group"] if classifications else None,
                original_quantity=Decimal("1"),
                remaining_quantity=Decimal("0"),
                unit_price=Decimal("100"),
            )
        )
        await connection.execute(
            SellLotAllocation.__table__.insert().values(
                id=ids["allocation"],
                sell_transaction_id=ids["sell_transaction"],
                buy_lot_id=ids["buy_lot"],
                quantity=Decimal("1"),
            )
        )
        if classifications:
            await connection.execute(
                TransactionLabel.__table__.insert().values(
                    transaction_id=ids["sell_transaction"],
                    label_id=ids["label"],
                )
            )
    return ids


async def _row_count(engine, table, **filters) -> int:
    statement = sa.select(sa.func.count()).select_from(table)
    for column_name, value in filters.items():
        statement = statement.where(table.c[column_name] == value)
    async with engine.connect() as connection:
        return (await connection.scalar(statement)) or 0


async def _assert_postgresql_delete_behavior(database_url: str) -> None:
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ids = await _seed_delete_graph(engine)
        async with sessions.begin() as session:
            transaction = await session.scalar(
                sa.select(Transaction)
                .where(Transaction.id == ids["buy_transaction"])
                .options(selectinload(Transaction.buy_lot))
            )
            assert transaction is not None
            await session.delete(transaction)
        assert await _row_count(engine, BuyLot.__table__, id=ids["buy_lot"]) == 0
        assert await _row_count(engine, SellLotAllocation.__table__, id=ids["allocation"]) == 0

        ids = await _seed_delete_graph(engine)
        async with sessions.begin() as session:
            transaction = await session.scalar(
                sa.select(Transaction)
                .where(Transaction.id == ids["sell_transaction"])
                .options(
                    selectinload(Transaction.sell_allocations),
                    selectinload(Transaction.transaction_labels),
                )
            )
            assert transaction is not None
            await session.delete(transaction)
        assert await _row_count(engine, SellLotAllocation.__table__, id=ids["allocation"]) == 0
        assert await _row_count(
            engine, TransactionLabel.__table__, transaction_id=ids["sell_transaction"]
        ) == 0

        ids = await _seed_delete_graph(engine)
        async with sessions.begin() as session:
            holding = await session.scalar(
                sa.select(Holding)
                .where(Holding.id == ids["holding"])
                .options(selectinload(Holding.buy_lots))
            )
            assert holding is not None
            await session.delete(holding)
        assert await _row_count(engine, Transaction.__table__, holding_id=ids["holding"]) == 0
        assert await _row_count(engine, BuyLot.__table__, holding_id=ids["holding"]) == 0
        assert await _row_count(engine, SellLotAllocation.__table__, id=ids["allocation"]) == 0

        ids = await _seed_delete_graph(engine, classifications=False)
        async with sessions.begin() as session:
            user = await session.scalar(
                sa.select(User)
                .where(User.id == ids["user"])
                .options(selectinload(User.buy_lots))
            )
            assert user is not None
            await session.delete(user)
        assert await _row_count(engine, User.__table__, id=ids["user"]) == 0
        assert await _row_count(engine, BuyLot.__table__, user_id=ids["user"]) == 0

        ids = await _seed_delete_graph(engine)
        async with sessions() as session:
            source_group = await session.scalar(
                sa.select(SourceGroup)
                .where(SourceGroup.id == ids["source_group"])
                .options(
                    selectinload(SourceGroup.memberships),
                    selectinload(SourceGroup.transactions),
                    selectinload(SourceGroup.buy_lots),
                )
            )
            assert source_group is not None
            await session.delete(source_group)
            with pytest.raises(sa.exc.IntegrityError):
                await session.flush()
            await session.rollback()
        assert await _row_count(engine, SourceGroup.__table__, id=ids["source_group"]) == 1
        assert await _row_count(
            engine, RollupGroupMember.__table__, source_group_id=ids["source_group"]
        ) == 1

        async with sessions() as session:
            rollup_group = await session.scalar(
                sa.select(RollupGroup)
                .where(RollupGroup.id == ids["rollup_group"])
                .options(selectinload(RollupGroup.members))
            )
            assert rollup_group is not None
            await session.delete(rollup_group)
            with pytest.raises(sa.exc.IntegrityError):
                await session.flush()
            await session.rollback()
        assert await _row_count(engine, RollupGroup.__table__, id=ids["rollup_group"]) == 1

        async with sessions() as session:
            label = await session.scalar(
                sa.select(Label)
                .where(Label.id == ids["label"])
                .options(selectinload(Label.transaction_labels))
            )
            assert label is not None
            await session.delete(label)
            with pytest.raises(sa.exc.IntegrityError):
                await session.flush()
            await session.rollback()
        assert await _row_count(engine, Label.__table__, id=ids["label"]) == 1
    finally:
        await engine.dispose()


def test_alembic_upgrade_and_database_owned_deletes_on_isolated_postgresql(
    isolated_postgresql_url: str,
) -> None:
    config = Config(str(BACKEND_PATH / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_PATH / "alembic"))
    config.set_main_option("sqlalchemy.url", isolated_postgresql_url)

    command.upgrade(config, "head")
    asyncio.run(_assert_postgresql_delete_behavior(isolated_postgresql_url))


def test_group_models_register_expected_tables() -> None:
    assert {
        "source_groups",
        "rollup_groups",
        "rollup_group_members",
        "labels",
        "buy_lots",
        "sell_lot_allocations",
        "transaction_labels",
    } <= set(Base.metadata.tables)


def test_group_models_expose_accounting_relationships() -> None:
    assert {"source_group", "buy_lot", "sell_allocations", "transaction_labels"} <= _relationship_names(Transaction)
    assert {"source_groups", "rollup_groups", "labels", "buy_lots"} <= _relationship_names(User)
    assert {"memberships", "transactions", "buy_lots"} <= _relationship_names(SourceGroup)
    assert {"members"} <= _relationship_names(RollupGroup)
    assert {"transaction_labels"} <= _relationship_names(Label)
    assert {"transaction", "holding", "user", "source_group", "sell_allocations"} <= _relationship_names(
        BuyLot
    )
    assert {"sell_transaction", "buy_lot"} <= _relationship_names(SellLotAllocation)
    assert {"rollup_group", "source_group"} <= _relationship_names(RollupGroupMember)
    assert {"transaction", "label"} <= _relationship_names(TransactionLabel)


def test_group_models_define_uniqueness_and_quantity_checks() -> None:
    buy_lots = BuyLot.__table__
    allocations = SellLotAllocation.__table__

    assert buy_lots.c.transaction_id.unique
    assert any(
        isinstance(constraint, sa.UniqueConstraint)
        and {column.name for column in constraint.columns} == {"sell_transaction_id", "buy_lot_id"}
        for constraint in allocations.constraints
    )
    assert {
        str(constraint.sqltext)
        for constraint in buy_lots.constraints
        if isinstance(constraint, sa.CheckConstraint)
    } == {
        "original_quantity > 0",
        "remaining_quantity >= 0",
        "remaining_quantity <= original_quantity",
        "unit_price > 0",
    }
    assert {
        str(constraint.sqltext)
        for constraint in allocations.constraints
        if isinstance(constraint, sa.CheckConstraint)
    } == {"quantity > 0"}


def test_expand_migration_uses_conservative_legacy_backfill() -> None:
    migration = MIGRATION_PATH.read_text()

    assert "down_revision: Union[str, None] = '1ea62c42a6ce'" in migration
    assert "legacy_holding_tag_counts" in migration
    assert "CASE WHEN legacy_tags.tag_count = 1 THEN legacy_tags.tag_id ELSE NULL END" in migration
    assert "SET source_group_id = CASE" in migration
    assert "transactions.source_group_id," in migration
    assert "WHERE transactions.type = 'BUY'" in migration
    assert "UPDATE transactions" in migration
    assert "SET requires_review = true" in migration
    assert "WHERE type = 'SELL'" in migration
    assert "drop_table('tags')" not in migration
    assert "drop_table('holding_tags')" not in migration


def test_requires_review_is_non_null_with_false_server_default() -> None:
    column = Transaction.__table__.c.requires_review

    assert not column.nullable
    assert str(column.server_default.arg) == "false"


def test_transaction_source_group_is_nullable_indexed_authoritative_reference() -> None:
    column = Transaction.__table__.c.source_group_id

    assert column.nullable
    assert column.index
    assert next(iter(column.foreign_keys)).target_fullname == "source_groups.id"


def test_referenced_classifications_use_restrict_foreign_keys() -> None:
    reference_columns = [
        Transaction.__table__.c.source_group_id,
        BuyLot.__table__.c.source_group_id,
        RollupGroupMember.__table__.c.source_group_id,
        RollupGroupMember.__table__.c.rollup_group_id,
        TransactionLabel.__table__.c.label_id,
    ]

    assert [next(iter(column.foreign_keys)).ondelete for column in reference_columns] == [
        "RESTRICT",
        "RESTRICT",
        "RESTRICT",
        "RESTRICT",
        "RESTRICT",
    ]


def test_database_owned_delete_relationships_are_passive() -> None:
    cascade_relationships = [
        (Holding, "buy_lots"),
        (Transaction, "buy_lot"),
        (Transaction, "sell_allocations"),
        (Transaction, "transaction_labels"),
        (User, "buy_lots"),
        (BuyLot, "sell_allocations"),
    ]
    restrictive_relationships = [
        (SourceGroup, "memberships"),
        (SourceGroup, "transactions"),
        (SourceGroup, "buy_lots"),
        (RollupGroup, "members"),
        (Label, "transaction_labels"),
    ]

    assert [
        _relationship(model, name).passive_deletes for model, name in cascade_relationships
    ] == ["all"] * len(cascade_relationships)
    assert [
        _relationship(model, name).passive_deletes for model, name in restrictive_relationships
    ] == ["all"] * len(restrictive_relationships)
    assert all(
        "delete" not in _relationship(model, name).cascade
        for model, name in restrictive_relationships
    )


def test_expand_migration_adds_authoritative_source_and_protected_references() -> None:
    migration = MIGRATION_PATH.read_text()

    assert "op.f('ix_transactions_source_group_id')" in migration
    assert "'fk_transactions_source_group_id_source_groups'" in migration
    assert migration.count("ondelete='RESTRICT'") == 5
    assert "op.drop_constraint('fk_transactions_source_group_id_source_groups', 'transactions', type_='foreignkey')" in migration
    assert "op.drop_column('transactions', 'source_group_id')" in migration
