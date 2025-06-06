from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker # Use async_sessionmaker
from sqlalchemy.orm import declarative_base
from fastapi import Request # Import Request

# from enableai_hub.core.config import AppSettings # Assuming AppSettings is in config.py
# For now, using a direct URL. Will be updated to use AppSettings later.
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/arcade_platform_db"

# Create an async engine
# echo=True is useful for debugging, prints all SQL statements
engine = create_async_engine(DATABASE_URL, echo=True)

# Create a session factory using async_sessionmaker
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base for declarative models
Base = declarative_base()

# Dependency for FastAPI to get a DB session
async def get_db_session(request: Request) -> AsyncSession: # Accept FastAPI Request
    async with AsyncSessionFactory() as session:
        # Store session in request.state for potential use by Authlib internals or other parts of the app
        if hasattr(request, "state"):
            request.state.db_session = session
        else:
            # This case should ideally not happen in FastAPI if request is always a Starlette Request.
            print("Warning: request.state not available in get_db_session. Session won't be stored in request.state.")

        try:
            yield session
            await session.commit() # Commit if no exceptions during request handling
        except Exception:
            await session.rollback() # Rollback on error
            raise
        finally:
            # No need to explicitly remove from request.state as session is closing.
            if hasattr(request, "state") and hasattr(request.state, "db_session"):
                del request.state.db_session # Clean up to be sure
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
