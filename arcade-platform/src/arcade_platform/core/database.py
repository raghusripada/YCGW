from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
# from arcade_platform.core.config import AppSettings # Assuming AppSettings is in config.py
# For now, using a direct URL. Will be updated to use AppSettings later.
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/arcade_platform_db"

# Create an async engine
# echo=True is useful for debugging, prints all SQL statements
engine = create_async_engine(DATABASE_URL, echo=True)

# Create a session factory
# expire_on_commit=False is often recommended for FastAPI use cases with async sessions
AsyncSessionFactory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base for declarative models
Base = declarative_base()

# Dependency for FastAPI to get a DB session
async def get_db_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit() # Commit if no exceptions during request handling
        except Exception:
            await session.rollback() # Rollback on error
            raise
        finally:
            await session.close()

# Function to create all tables (useful for initial setup without Alembic, or for tests)
# In production, Alembic handles table creation and migrations.
async def create_tables():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Use with caution: drops all tables
        await conn.run_sync(Base.metadata.create_all)

# Function to drop all tables (useful for tests)
async def drop_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
