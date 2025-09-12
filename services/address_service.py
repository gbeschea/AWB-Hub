# services/address_service.py
import logging
import re
from typing import Dict, Tuple, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from rapidfuzz import process, fuzz

import models

ARTERA_KEYWORDS = [
    'strada', 'str', 'bulevardul', 'bd', 'calea', 'cal', 
    'drumul', 'soseaua', 'sos', 'aleea', 'intrarea', 'intr',
    'prelungirea', 'prel', 'piata'
]
ARTERA_KEYWORDS.sort(key=len, reverse=True)

TITLES_TO_REMOVE = [
    'arhitect', 'arh', 'doctor', 'dr', 'general', 'g-ral', 'colonel', 'col',
    'plutonier', 'plt', 'capitan', 'cap'
]

class AddressValidator:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    def _normalize_string(self, text: Optional[str]) -> str:
        if not text: return ""
        text = text.lower().strip()
        # Pas 1: Diacritice - Dictionar complet
        replacements = {'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ț': 't'}
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        # Pas 2: Punctuație și caractere speciale devin spațiu
        text = re.sub(r'[\.,;()/]', ' ', text)
        # Pas 3: Normalizăm spațiile multiple
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _normalize_localitate(self, localitate: str) -> List[str]:
        norm = self._normalize_string(localitate)
        if 'sector' in norm: return ['bucuresti']
        potential_localitati = re.findall(r'[\w-]+', norm)
        if 'tg' in potential_localitati:
            potential_localitati.append('targu ' + ' '.join([p for p in potential_localitati if p != 'tg']))
        return list(set(potential_localitati))

    def _parse_strada(self, strada_completa: str, localitate: str = "", judet: str = "") -> str:
        # Folosim o copie pentru a nu modifica originalul in timpul procesarii
        strada_curatata = strada_completa.lower()

        # Eliminăm localitatea și județul
        if localitate: strada_curatata = strada_curatata.replace(localitate.lower(), '')
        if judet: strada_curatata = strada_curatata.replace(judet.lower(), '')

        # Eliminăm "zgomotul" (nr, bl, sc, ap, etc.) indiferent de pozitie
        noise_patterns = r'\b(nr|numar|bl|bloc|sc|scara|et|etaj|ap|apartament|easybox|pizza davidone)[\s\.]*\w*'
        strada_curatata = re.sub(noise_patterns, '', strada_curatata, flags=re.IGNORECASE)
        
        # Eliminăm titlurile
        for title in TITLES_TO_REMOVE:
            strada_curatata = re.sub(r'\b' + title + r'\b', '', strada_curatata, flags=re.IGNORECASE)

        strada_norm = self._normalize_string(strada_curatata)

        # Eliminăm tipurile de arteră
        for keyword in ARTERA_KEYWORDS:
            if strada_norm.startswith(keyword + ' '):
                strada_norm = strada_norm[len(keyword):].strip()
                break
        
        return strada_norm

    async def _find_and_correct_localitate(self, potential_localitati: List[str], judet_norm: str) -> Optional[Tuple[str, str]]:
        # ... funcția rămâne la fel ...
        q_exact = select(models.RomaniaAddress.localitate).where(
            func.unaccent(func.lower(models.RomaniaAddress.judet)) == judet_norm,
            func.unaccent(func.lower(models.RomaniaAddress.localitate)).in_(potential_localitati)
        ).distinct()
        result_exact = await self.db.execute(q_exact)
        found_exact = result_exact.scalars().first()
        if found_exact:
            return self._normalize_string(found_exact), found_exact

        q_all_localitati = select(models.RomaniaAddress.localitate).where(
            func.unaccent(func.lower(models.RomaniaAddress.judet)) == judet_norm
        ).distinct()
        result_all = await self.db.execute(q_all_localitati)
        all_localitati_db = result_all.scalars().all()
        
        if not all_localitati_db: return None
        
        best_match = process.extractOne(
            potential_localitati[0], 
            {self._normalize_string(loc): loc for loc in all_localitati_db}.items(),
            scorer=fuzz.ratio,
            score_cutoff=95
        )
        
        if best_match:
            return best_match[0][0], best_match[0][1]
            
        return None
    
    async def _get_nume_strazi_for_localitate(self, localitate_norm: str, judet_norm: str) -> List[str]:
        # ... funcția rămâne la fel ...
        q = select(models.RomaniaAddress.nume_strada).where(
            func.unaccent(func.lower(models.RomaniaAddress.localitate)) == localitate_norm,
            func.unaccent(func.lower(models.RomaniaAddress.judet)) == judet_norm,
            models.RomaniaAddress.nume_strada.isnot(None)
        )
        result = await self.db.execute(q)
        return [self._normalize_string(row[0]) for row in result if row[0]]

    async def validate_order_address(self, order: models.Order) -> Tuple[str, int, Dict]:
        logging.info(f"Se validează adresa pentru comanda {order.name}...")
        score, errors, info = 100, {}, {}
        
        judet_input = order.shipping_province
        localitate_input = order.shipping_city
        zip_input = order.shipping_zip
        strada_input = order.shipping_address1 or ""

        if not all([judet_input, localitate_input, strada_input]):
            errors['completitudine'] = "Județul, localitatea și strada sunt obligatorii."
            score = 0
            order.address_status = 'invalid'; order.address_score = 0; order.address_validation_errors = errors
            return 'invalid', 0, errors

        judet_norm = self._normalize_string(judet_input)
        potential_localitati = self._normalize_localitate(localitate_input)
        zip_norm = self._normalize_string(zip_input)

        # Logica de Triangulare...
        judet_validat, localitate_validata = judet_input, localitate_input
        
        # Scenariul 1: Prioritizăm ZIP-ul
        if zip_norm and len(zip_norm) == 6 and zip_norm.isdigit():
            q_zip = select(models.RomaniaAddress.judet, models.RomaniaAddress.localitate).where(models.RomaniaAddress.cod_postal == zip_norm).distinct()
            res_zip = await self.db.execute(q_zip)
            zip_matches = res_zip.all()
            if len(zip_matches) == 1:
                db_judet, db_localitate = zip_matches[0]
                if self._normalize_string(db_judet) != judet_norm:
                    info['corectie_judet_zip'] = f"Județul '{judet_input}' corectat în '{db_judet}' (ZIP)."
                    judet_validat = db_judet
                if self._normalize_string(db_localitate) != self._normalize_localitate(localitate_input)[0]:
                    info['corectie_localitate_zip'] = f"Localitatea '{localitate_input}' corectată în '{db_localitate}' (ZIP)."
                    localitate_validata = db_localitate
        
        # Scenariul 2: Județ + Localitate
        correction_result = await self._find_and_correct_localitate(potential_localitati, judet_norm)
        if not correction_result:
            score -= 70
            errors['localitate_judet'] = f"Combinația '{localitate_input}' / '{judet_input}' nu a fost găsită."
        else:
            _, localitate_corectata = correction_result
            if localitate_input != localitate_corectata:
                info['auto_corectie'] = f"Localitatea '{localitate_input}' a fost corectată în '{localitate_corectata}'."
                localitate_validata = localitate_corectata

        if 'localitate_judet' not in errors:
            nume_strada_parsata = self._parse_strada(strada_input, localitate_validata, judet_validat)
            if not nume_strada_parsata:
                errors['strada'] = "Numele străzii pare a fi gol după curățare."; score -= 60
            else:
                nume_strazi_db = await self._get_nume_strazi_for_localitate(self._normalize_string(localitate_validata), self._normalize_string(judet_validat))
                if nume_strazi_db:
                    suggestion = process.extractOne(nume_strada_parsata, nume_strazi_db, scorer=fuzz.token_set_ratio, score_cutoff=80)
                    if not suggestion:
                        score -= 40
                        errors['strada'] = f"Strada '{strada_input}' nu a fost găsită în {localitate_validata}."
                    elif suggestion[1] < 100:
                        score -= (100 - suggestion[1])
                        errors['strada'] = f"Potrivire parțială pentru '{strada_input}'. Sugestie: '{suggestion[0].title()}'?"

        # Actualizăm comanda
        order.shipping_province = judet_validat
        order.shipping_city = localitate_validata
        
        final_status = 'valid' if not errors else 'invalid'
        order.address_status = final_status
        order.address_score = max(0, int(score))
        order.address_validation_errors = {**errors, **info}
        
        logging.info(f"Validare finalizată pentru {order.name}: Status={final_status}, Scor={int(score)}, Erori={order.address_validation_errors}")
        return final_status, int(score), errors


async def validate_address_for_order(db: AsyncSession, order: models.Order):
    validator = AddressValidator(db)
    await validator.validate_order_address(order)