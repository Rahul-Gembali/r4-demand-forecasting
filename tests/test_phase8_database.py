"""Unit and integration tests for Phase 8: Database Data Model and Persistence.

Covers:
- Schema registration and table metadata
- Master SKU catalogue CRUD, filtering, and pagination
- Store cluster and holiday calendar persistence
- Model version registry and execution runs
- Duplicate-run execution protection
- Conformal prediction intervals and unique constraint enforcement
- Cascade deletes across relational hierarchies
- Transaction rollback safety
- Cold-start confidence ranking and executive summary queries
- Strict data isolation of evaluation SKU sales
- Cryptographic data lineage manifests
"""

from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.db.models import (
    Base,
    HolidayModel,
    InventoryRecommendationModel,
    SKUModel,
    WeeklyForecastModel,
    WeeklySalesModel,
)
from src.db.repository import DuplicateRunError, ForecastRepository
from src.db.session import create_async_db_engine, drop_db_schema, init_db_schema


@pytest_asyncio.fixture
async def test_db_engine(tmp_path: Path) -> AsyncEngine:
    """Create isolated temporary file-based SQLite async engine for tests."""
    db_file = tmp_path / "test_phase8.db"
    engine = create_async_db_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}", echo=False)
    await init_db_schema(engine)
    yield engine
    await drop_db_schema(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine: AsyncEngine) -> AsyncSession:
    """Yield an active transactional async session."""
    session_factory = async_sessionmaker(
        bind=test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_schema_models_registration():
    """Verify all 11 required normalized tables are registered in SQLAlchemy metadata."""
    expected_tables = {
        "skus",
        "store_clusters",
        "holidays",
        "weekly_sales",
        "model_versions",
        "forecast_runs",
        "weekly_forecasts",
        "analogue_matches",
        "inventory_recommendations",
        "cluster_allocations",
        "data_manifests",
    }
    registered = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(registered), f"Missing tables: {expected_tables - registered}"


@pytest.mark.asyncio
async def test_sku_crud_and_pagination(test_db_session: AsyncSession):
    """Test SKU creation, retrieval, filtering, and pagination."""
    repo = ForecastRepository(test_db_session)

    skus_data = [
        {
            "sku_id": f"SKU_TEST_{i:03d}",
            "product_name": f"Test Product {i}",
            "category": "Apparel" if i % 2 == 0 else "Footwear",
            "subcategory": "Jackets" if i % 2 == 0 else "Sneakers",
            "base_price": 50.0 + i,
            "launch_date": date(2025, 1, 1),
            "is_evaluation_sku": i >= 5,
        }
        for i in range(10)
    ]
    inserted = await repo.bulk_upsert_skus(skus_data)
    assert inserted == 10

    # Retrieve single SKU
    sku = await repo.get_sku("SKU_TEST_003")
    assert sku is not None
    assert sku.category == "Footwear"
    assert sku.is_evaluation_sku is False

    # Test Pagination (first page)
    page1, total = await repo.list_skus(limit=4, offset=0)
    assert total == 10
    assert len(page1) == 4
    assert page1[0].sku_id == "SKU_TEST_000"

    # Test Pagination (second page)
    page2, _ = await repo.list_skus(limit=4, offset=4)
    assert len(page2) == 4
    assert page2[0].sku_id == "SKU_TEST_004"

    # Test Filtering by is_evaluation_sku
    eval_skus, eval_total = await repo.list_skus(is_evaluation_sku=True)
    assert eval_total == 5
    assert len(eval_skus) == 5
    assert all(s.is_evaluation_sku for s in eval_skus)


@pytest.mark.asyncio
async def test_store_clusters_and_holidays(test_db_session: AsyncSession):
    """Test store cluster and holiday calendar insertion and unique constraints."""
    repo = ForecastRepository(test_db_session)

    # Store Clusters
    clusters = [
        {"cluster_id": "CL_1", "cluster_name": "Flagship High Volume", "store_count": 3},
        {"cluster_id": "CL_2", "cluster_name": "Regional Suburban", "store_count": 4},
    ]
    await repo.bulk_insert_store_clusters(clusters)
    fetched_clusters = await repo.list_store_clusters()
    assert len(fetched_clusters) == 2

    # Holidays
    holidays = [
        {"holiday_name": "New Year", "holiday_date": date(2025, 1, 1), "week_of_year": 1, "year": 2025, "is_promotional": True},
        {"holiday_name": "Easter", "holiday_date": date(2025, 4, 20), "week_of_year": 16, "year": 2025, "is_promotional": False},
    ]
    await repo.bulk_insert_holidays(holidays)

    # Test Unique Constraint on (holiday_name, holiday_date)
    dup_holiday = HolidayModel(
        holiday_name="New Year",
        holiday_date=date(2025, 1, 1),
        week_of_year=1,
        year=2025,
    )
    test_db_session.add(dup_holiday)
    with pytest.raises(IntegrityError):
        await test_db_session.flush()
    await test_db_session.rollback()


@pytest.mark.asyncio
async def test_model_version_and_forecast_run(test_db_session: AsyncSession):
    """Test model version registration and forecast run tracking."""
    repo = ForecastRepository(test_db_session)

    # Register Model Version
    model = await repo.create_model_version(
        {
            "model_id": "catboost_test_v1",
            "algorithm": "CatBoostRegressor",
            "objective": "MAE",
            "target_transform": "log1p",
            "artifact_path": "artifacts/test_model.cbm",
            "validation_wape": 0.3150,
            "hyperparameters": {"iterations": 200, "depth": 6},
            "feature_schema": {"features": ["age", "price", "category"]},
        }
    )
    assert model.model_id == "catboost_test_v1"

    # Create Forecast Run
    run = await repo.create_forecast_run(
        {
            "run_id": "RUN_TEST_001",
            "model_id": "catboost_test_v1",
            "run_type": "TEST_RUN",
            "status": "RUNNING",
            "sku_count": 50,
            "reproducibility_seed": 42,
        }
    )
    assert run.status == "RUNNING"

    # Update status to COMPLETED
    updated = await repo.update_forecast_run_status(
        run_id="RUN_TEST_001",
        status="COMPLETED",
        overall_wape=0.3120,
        overall_bias_pct=-2.5,
    )
    assert updated.status == "COMPLETED"
    assert float(updated.overall_wape) == 0.3120
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_duplicate_run_protection(test_db_session: AsyncSession):
    """Ensure completed forecast runs cannot be inadvertently re-executed or overwritten."""
    repo = ForecastRepository(test_db_session)

    await repo.create_model_version(
        {
            "model_id": "model_dup_test",
            "algorithm": "CatBoost",
            "objective": "MAE",
            "target_transform": "log1p",
            "artifact_path": "dummy.cbm",
        }
    )

    # Create completed run
    await repo.create_forecast_run(
        {
            "run_id": "RUN_LOCKED",
            "model_id": "model_dup_test",
            "status": "COMPLETED",
        }
    )

    # Re-running with prevent_duplicates=True should raise DuplicateRunError
    with pytest.raises(DuplicateRunError) as exc_info:
        await repo.create_forecast_run(
            {
                "run_id": "RUN_LOCKED",
                "model_id": "model_dup_test",
                "status": "PENDING",
            },
            prevent_duplicates=True,
        )
    assert "already COMPLETED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_weekly_forecasts_and_unique_constraint(test_db_session: AsyncSession):
    """Test weekly point forecasts, intervals, and composite unique constraints."""
    repo = ForecastRepository(test_db_session)

    # Setup parent SKU and Run
    await repo.upsert_sku(
        {
            "sku_id": "SKU_FC_TEST",
            "product_name": "Forecast Product",
            "category": "Apparel",
            "subcategory": "Hoodies",
            "base_price": 79.99,
            "launch_date": date(2025, 2, 1),
            "is_evaluation_sku": True,
        }
    )
    await repo.create_model_version(
        {"model_id": "m_fc", "algorithm": "LGBM", "objective": "L1", "target_transform": "none", "artifact_path": "p"}
    )
    await repo.create_forecast_run(
        {"run_id": "RUN_FC_1", "model_id": "m_fc", "status": "COMPLETED", "sku_count": 1}
    )

    # Save 8-week predictions
    forecasts = [
        {
            "sku_id": "SKU_FC_TEST",
            "horizon_week": week,
            "predicted_sales": 100.0 - week * 5,
            "lower_bound_80": 80.0 - week * 5,
            "upper_bound_80": 120.0 - week * 5,
            "lower_bound_90": 70.0 - week * 5,
            "upper_bound_90": 130.0 - week * 5,
        }
        for week in range(1, 9)
    ]
    saved = await repo.save_weekly_forecasts("RUN_FC_1", forecasts)
    assert saved == 8

    # Test Unique Constraint Violation for duplicate (run_id, sku_id, horizon_week)
    duplicate_record = WeeklyForecastModel(
        run_id="RUN_FC_1",
        sku_id="SKU_FC_TEST",
        horizon_week=1,
        predicted_sales=99.0,
    )
    test_db_session.add(duplicate_record)
    with pytest.raises(IntegrityError):
        await test_db_session.flush()
    await test_db_session.rollback()


@pytest.mark.asyncio
async def test_cascade_delete_forecast_run(test_db_session: AsyncSession):
    """Verify deleting a forecast run cascades to its forecasts, matches, and recommendations."""
    repo = ForecastRepository(test_db_session)

    await repo.upsert_sku(
        {
            "sku_id": "SKU_DEL_1",
            "product_name": "Delete Me",
            "category": "Home",
            "subcategory": "Kitchen",
            "base_price": 25.0,
            "launch_date": date(2025, 3, 1),
        }
    )
    await repo.create_model_version(
        {"model_id": "m_del", "algorithm": "CatBoost", "objective": "MAE", "target_transform": "none", "artifact_path": "x"}
    )
    await repo.create_forecast_run(
        {"run_id": "RUN_CASCADE", "model_id": "m_del", "status": "COMPLETED"}
    )

    await repo.save_weekly_forecasts(
        "RUN_CASCADE",
        [{"sku_id": "SKU_DEL_1", "horizon_week": 1, "predicted_sales": 50.0}],
    )
    await repo.save_inventory_recommendations(
        "RUN_CASCADE",
        [
            {
                "sku_id": "SKU_DEL_1",
                "scenario": "BASE",
                "forecast_cumulative_8w": 400.0,
                "recommended_buy_quantity": 420,
                "critical_ratio": 0.65,
                "understock_cost_cu": 20.0,
                "overstock_cost_co": 10.0,
                "confidence_score": 75.0,
            }
        ],
    )

    # Delete the run
    deleted = await repo.delete_forecast_run("RUN_CASCADE")
    assert deleted is True

    # Verify forecasts and recommendations were cascade deleted
    f_count = (
        await test_db_session.execute(
            select(func.count(WeeklyForecastModel.id)).where(WeeklyForecastModel.run_id == "RUN_CASCADE")
        )
    ).scalar_one()
    assert f_count == 0

    r_count = (
        await test_db_session.execute(
            select(func.count(InventoryRecommendationModel.id)).where(InventoryRecommendationModel.run_id == "RUN_CASCADE")
        )
    ).scalar_one()
    assert r_count == 0


@pytest.mark.asyncio
async def test_transaction_rollback_on_failure(test_db_engine: AsyncEngine):
    """Test that session rollback ensures atomic all-or-nothing execution."""
    session_factory = async_sessionmaker(bind=test_db_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        repo = ForecastRepository(session)
        await repo.upsert_sku(
            {
                "sku_id": "SKU_ATOMIC_1",
                "product_name": "Atomic Product",
                "category": "Home",
                "subcategory": "Bedding",
                "base_price": 40.0,
                "launch_date": date(2025, 1, 1),
            }
        )
        await session.commit()

    # Now attempt a flawed batch that should rollback completely
    async with session_factory() as session:
        try:
            # 1. Valid SKU
            session.add(
                SKUModel(
                    sku_id="SKU_ATOMIC_2",
                    product_name="Second Product",
                    category="Home",
                    subcategory="Bedding",
                    base_price=45.0,
                    launch_date=date(2025, 1, 1),
                )
            )
            # 2. Duplicate SKU that violates primary key constraint
            session.add(
                SKUModel(
                    sku_id="SKU_ATOMIC_1",
                    product_name="Duplicate PK",
                    category="Home",
                    subcategory="Bedding",
                    base_price=50.0,
                    launch_date=date(2025, 1, 1),
                )
            )
            await session.flush()
            await session.commit()
        except IntegrityError:
            await session.rollback()

    # Verify SKU_ATOMIC_2 was NOT committed
    async with session_factory() as session:
        repo = ForecastRepository(session)
        sku2 = await repo.get_sku("SKU_ATOMIC_2")
        assert sku2 is None, "SKU_ATOMIC_2 should have been rolled back!"


@pytest.mark.asyncio
async def test_least_confident_skus_and_run_summary(test_db_session: AsyncSession):
    """Verify confidence ranking query and executive run summary calculations."""
    repo = ForecastRepository(test_db_session)

    # Create SKUs
    for i in range(1, 6):
        await repo.upsert_sku(
            {
                "sku_id": f"SKU_CONF_{i}",
                "product_name": f"Confidence Test {i}",
                "category": "Accessories",
                "subcategory": "Hats",
                "base_price": 30.0,
                "launch_date": date(2025, 1, 1),
                "is_evaluation_sku": True,
            }
        )

    await repo.create_model_version(
        {"model_id": "m_conf", "algorithm": "CatBoost", "objective": "MAE", "target_transform": "none", "artifact_path": "m"}
    )
    await repo.create_forecast_run(
        {
            "run_id": "RUN_CONF_TEST",
            "model_id": "m_conf",
            "status": "COMPLETED",
            "sku_count": 5,
            "overall_wape": 0.32,
            "overall_bias_pct": -4.0,
        }
    )

    # Save recommendations with deliberate confidence scores: [90, 45, 60, 35, 80]
    scores = [90.0, 45.0, 60.0, 35.0, 80.0]
    recs = [
        {
            "sku_id": f"SKU_CONF_{i}",
            "scenario": "BASE",
            "forecast_cumulative_8w": 500.0,
            "recommended_buy_quantity": 520,
            "critical_ratio": 0.65,
            "understock_cost_cu": 15.0,
            "overstock_cost_co": 10.0,
            "expected_total_cost": 1500.0,
            "expected_fill_rate_pct": 96.5,
            "confidence_score": scores[i - 1],
            "confidence_tier": "LOW" if scores[i - 1] < 55 else "HIGH",
            "explanation_summary": f"Summary for {i}",
        }
        for i in range(1, 6)
    ]
    await repo.save_inventory_recommendations("RUN_CONF_TEST", recs)

    # Query 3 least-confident SKUs (ordered ASC)
    bottom3 = await repo.get_least_confident_skus("RUN_CONF_TEST", limit=3)
    assert len(bottom3) == 3
    assert bottom3[0]["sku_id"] == "SKU_CONF_4"  # score 35.0
    assert bottom3[1]["sku_id"] == "SKU_CONF_2"  # score 45.0
    assert bottom3[2]["sku_id"] == "SKU_CONF_3"  # score 60.0

    # Query run summary
    summary = await repo.get_run_summary("RUN_CONF_TEST")
    assert summary is not None
    assert summary["sku_count"] == 5
    assert summary["total_recommended_buy_units"] == 520 * 5
    assert summary["total_expected_cost"] == 1500.0 * 5
    assert abs(summary["average_confidence_score"] - sum(scores) / len(scores)) < 1e-4


@pytest.mark.asyncio
async def test_data_isolation_enforcement(test_db_session: AsyncSession):
    """Enforce architectural security rule: zero sales observations permitted for evaluation SKUs."""
    repo = ForecastRepository(test_db_session)

    # Cluster
    await repo.bulk_insert_store_clusters([{"cluster_id": "CL_ISO", "cluster_name": "Cluster", "store_count": 1}])

    # Mature SKU vs Evaluation SKU
    await repo.upsert_sku(
        {
            "sku_id": "SKU_MATURE_ISO",
            "product_name": "Mature SKU",
            "category": "Apparel",
            "subcategory": "Pants",
            "base_price": 50.0,
            "launch_date": date(2024, 1, 1),
            "is_evaluation_sku": False,
        }
    )
    await repo.upsert_sku(
        {
            "sku_id": "SKU_EVAL_ISO",
            "product_name": "Evaluation SKU",
            "category": "Apparel",
            "subcategory": "Pants",
            "base_price": 50.0,
            "launch_date": date(2025, 1, 1),
            "is_evaluation_sku": True,
        }
    )

    # Ingest sales for mature SKU
    await repo.bulk_insert_weekly_sales(
        [
            {
                "sku_id": "SKU_MATURE_ISO",
                "store_id": "STORE_01",
                "cluster_id": "CL_ISO",
                "launch_week_age": 1,
                "units_sold": 25.0,
            }
        ]
    )

    # Assert 0 sales for any evaluation SKU
    leak_stmt = (
        select(func.count(WeeklySalesModel.id))
        .join(SKUModel, WeeklySalesModel.sku_id == SKUModel.sku_id)
        .where(SKUModel.is_evaluation_sku.is_(True))
    )
    leak_count = (await test_db_session.execute(leak_stmt)).scalar_one()
    assert leak_count == 0, "Hidden evaluation labels leaked into sales table!"


@pytest.mark.asyncio
async def test_data_manifest_persistence(test_db_session: AsyncSession):
    """Verify cryptographic provenance and lineage audit logging."""
    repo = ForecastRepository(test_db_session)

    manifest_data = {
        "manifest_type": "PROCESSED_FORECASTS",
        "file_identifier": "data/processed/forecasts_with_intervals_150_skus.csv",
        "sha256_checksum": "a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
        "row_count": 1200,
        "schema_snapshot": {"columns": 12, "format": "csv"},
    }
    manifest = await repo.record_data_manifest(manifest_data)
    assert manifest.id is not None

    lookup = await repo.get_manifest_by_checksum("a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef")
    assert lookup is not None
    assert lookup.manifest_type == "PROCESSED_FORECASTS"
    assert lookup.row_count == 1200


def test_alembic_migration_upgrade_and_downgrade(tmp_path: Path):
    """Test executing Alembic migrations upgrade to head, downgrade to base, and re-upgrade."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "alembic_lifecycle.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")

    # 1. Upgrade to head
    command.upgrade(cfg, "head")

    # 2. Downgrade to base
    command.downgrade(cfg, "base")

    # 3. Re-upgrade to head
    command.upgrade(cfg, "head")
