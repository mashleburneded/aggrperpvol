from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base # Replaced declarative_base from ext.declarative
from .config import settings
import logging

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Create an async engine
try:
    # Ensure the URL is compatible with asyncpg if using PostgreSQL
    async_db_url = SQLALCHEMY_DATABASE_URL
    if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
        async_db_url = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif SQLALCHEMY_DATABASE_URL.startswith("postgres://"): # Common in some environments
        async_db_url = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)


    engine = create_async_engine(async_db_url, echo=settings.DB_ECHO)
    logger.info(f"Async database engine created for URL (adjusted for asyncpg): {async_db_url}")
except Exception as e:
    logger.error(f"Failed to create async database engine with URL {SQLALCHEMY_DATABASE_URL}: {e}")
    # Fallback or raise critical error depending on desired behavior
    # For now, let it raise to make the issue visible during startup
    raise

# Create an async session factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

# Async dependency to get DB session
async def get_async_db() -> AsyncSession:
    async_session = AsyncSessionLocal()
    try:
        yield async_session
        await async_session.commit() # Commit changes if no exceptions
    except Exception as e:
        await async_session.rollback() # Rollback on error
        logger.error(f"Database session error: {e}", exc_info=True)
        raise # Re-raise the exception to be handled by FastAPI error handlers
    finally:
        await async_session.close()

# Async function to create all tables
async def create_db_and_tables():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Optional: for clean slate during dev
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (if they didn't exist).")

# Synchronous parts (if still needed by any non-async part, e.g. Alembic offline mode)
# For a fully async app, these might not be necessary.
# from sqlalchemy import create_engine as create_sync_engine
# sync_engine = create_sync_engine(SQLALCHEMY_DATABASE_URL)
# SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# def get_db(): # Synchronous version, if needed
#     db = SyncSessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()
