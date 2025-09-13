from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Încarcă variabilele de mediu din fișierul .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Creează motorul asincron pentru baza de date
engine = create_async_engine(DATABASE_URL, echo=True)

# Creează o fabrică de sesiuni asincrone
AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

async def get_db():
    """
    Dependency care furnizează o sesiune de bază de date la fiecare cerere.
    """
    async with AsyncSessionLocal() as session:
        yield session