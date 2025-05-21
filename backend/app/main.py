import logging
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession # Import AsyncSession
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import date, timedelta, datetime, timezone

# Updated database imports for async
from .core.database import create_db_and_tables, get_async_db, engine as async_engine 
from . import models, schemas # crud is not directly used here now
from .api import api_keys_router, volume_router
from .services.aggregation_service import AggregationService
from .core.cache import startup_redis_pool, shutdown_redis_pool, set_cache
from .core.config import settings # For HISTORICAL_DATA_FETCH_DAYS

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")

# No longer need synchronous get_db or SessionLocal here

async def run_historical_data_fetch_job():
    logger.info(f"Scheduler: Running historical data fetch job at {datetime.now(timezone.utc)}")
    async_session_gen = get_async_db()
    db: AsyncSession = await async_session_gen.__anext__()
    try:
        agg_service = AggregationService(db)
        # Fetch for the last N days up to yesterday, N from settings
        end_date_dt = datetime.now(timezone.utc) - timedelta(days=1)
        start_date_dt = end_date_dt - timedelta(days=settings.HISTORICAL_DATA_FETCH_DAYS)
        
        await agg_service.fetch_and_store_historical_data_for_all_active_platforms(
            start_date=start_date_dt, # Pass datetime objects
            end_date=end_date_dt
        )
        logger.info("Scheduler: Historical data fetch job completed.")
    except Exception as e:
        logger.error(f"Scheduler: Error in historical data fetch job: {e}", exc_info=True)
    finally:
        try:
            # Ensure the generator is exhausted to close the session
            await async_session_gen.__anext__() 
        except StopAsyncIteration:
            pass # Expected
        except Exception as e:
            logger.error(f"Scheduler: Error closing session in historical job: {e}", exc_info=True)


async def run_current_volume_cache_job():
    logger.info(f"Scheduler: Running current volume cache job at {datetime.now(timezone.utc)}")
    async_session_gen = get_async_db()
    db: AsyncSession = await async_session_gen.__anext__()
    try:
        agg_service = AggregationService(db)
        # AggregationService.get_current_aggregated_volume now handles caching internally
        # and doesn't require platform_symbol_map as an argument.
        current_volume_data = await agg_service.get_current_aggregated_volume()
        
        # The service itself now handles caching, so no need to explicitly set_cache here.
        # If we still want to log, we can.
        logger.info(f"Scheduler: Current aggregated volume fetched (and cached by service): {current_volume_data.total_volume_24h_usd}")
        logger.info("Scheduler: Current volume cache job completed.")
    except Exception as e:
        logger.error(f"Scheduler: Error in current volume cache job: {e}", exc_info=True)
    finally:
        try:
            await async_session_gen.__anext__()
        except StopAsyncIteration:
            pass
        except Exception as e:
            logger.error(f"Scheduler: Error closing session in current volume job: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application startup...")
    await create_db_and_tables() # Call the async version
    await startup_redis_pool()
    
    scheduler.add_job(run_historical_data_fetch_job, "cron", hour=settings.SCHEDULER_HISTORICAL_HOUR_UTC, minute=0, misfire_grace_time=900) 
    scheduler.add_job(run_current_volume_cache_job, "interval", minutes=settings.SCHEDULER_CURRENT_VOLUME_MINUTES, misfire_grace_time=60)
    
    scheduler.start()
    logger.info("Scheduler started.")
    yield
    # Shutdown
    logger.info("Application shutdown...")
    await shutdown_redis_pool()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")
    
    # Dispose the engine to close all connections
    await async_engine.dispose()
    logger.info("Database engine disposed.")


app = FastAPI(
    title="Aggregated Perpetual Volume API",
    description="API to provide aggregated trading volume data from various exchanges.",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(api_keys_router.router, prefix="/api/v1/keys", tags=["API Keys"])
app.include_router(volume_router.router, prefix="/api/v1/volume", tags=["Volume Data"])

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Aggregated Perpetual Volume API"}

# Basic logging configuration (can be expanded)
logging.basicConfig(level=settings.LOG_LEVEL.upper(), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Ensure all models are imported so Base.metadata knows about them
# This is usually handled by importing them in models/__init__.py and then importing that package
# For explicitness here, or if __init__ is not set up for that:
from .models import api_key, historical_volume 
# This ensures Base.metadata.create_all(bind=engine) in database.py knows about these tables.
