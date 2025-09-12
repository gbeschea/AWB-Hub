# scripts/import_addresses.py
import asyncio
import csv
import sys
from pathlib import Path

# --- Varianta Corectă ---
# Adaugă directorul rădăcină în path pentru a putea importa modulele aplicației
# Această linie determină calea automat și este metoda corectă
sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert

from database import DATABASE_URL
from models import RomaniaAddress

async def main():
    # Asigură-te că ai un fișier 'addresses.csv' în acest director
    # Format CSV așteptat: judet,localitate,strada,cod_postal,sector
    csv_path = Path(__file__).parent / "addresses.csv"
    if not csv_path.exists():
        print(f"EROARE: Fișierul {csv_path} nu a fost găsit.")
        print("Te rog asigură-te că fișierul 'addresses.csv' se află în directorul 'scripts'.")
        return

    print("Se conectează la baza de date...")
    engine = create_async_engine(DATABASE_URL)
    AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession)

    print(f"Se citesc datele din {csv_path}...")
    try:
        with open(csv_path, mode='r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            addresses_to_insert = [
                {
                    "judet": row.get("judet"),
                    "localitate": row.get("localitate"),
                    # Citim direct din coloanele tale
                    "tip_artera": row.get("tip artera") or None, 
                    "nume_strada": row.get("denumire artera") or None,
                    "cod_postal": row.get("codpostal"), # Atenție, 'codpostal' fără '_' în screenshot-ul tău
                    "sector": row.get("sector") or None,
                }
                for row in reader
            ]

    except Exception as e:
        print(f"EROARE la citirea fișierului CSV: {e}")
        print("Verifică dacă fișierul este salvat cu encoding 'UTF-8' și dacă numele coloanelor sunt corecte.")
        return

    if not addresses_to_insert:
        print("Nu s-au găsit adrese de importat.")
        return

    print(f"S-au găsit {len(addresses_to_insert)} adrese. Se începe inserarea în baza de date...")
    
    async with AsyncSessionLocal() as session:
        async with session.begin():
            print("Se șterg datele existente din tabela 'romania_addresses'...")
            await session.execute(RomaniaAddress.__table__.delete())

            batch_size = 5000
            for i in range(0, len(addresses_to_insert), batch_size):
                batch = addresses_to_insert[i:i + batch_size]
                await session.execute(insert(RomaniaAddress).values(batch))
                print(f"S-au inserat {i + len(batch)} / {len(addresses_to_insert)} adrese...")
        
        await session.commit()

    print("Importul a fost finalizat cu succes!")


if __name__ == "__main__":
    asyncio.run(main())