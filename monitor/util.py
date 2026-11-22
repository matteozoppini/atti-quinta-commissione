"""Funzioni di supporto: normalizzazione di nomi e testi, date."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta


def senza_accenti(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s: str) -> str:
    """Maiuscolo, senza accenti/apostrofi/punteggiatura, spazi compattati."""
    s = senza_accenti(s).upper()
    s = s.replace("’", "'").replace("'", " ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def chiave_persona(nome: str) -> str:
    """'BACCI Lorenzo' e 'Lorenzo BACCI' producono la stessa chiave."""
    return " ".join(sorted(norm(nome).split()))


def norm_settore(nome: str) -> str:
    n = norm(nome)
    n = re.sub(r"^SETTORE ", "", n)
    return n


def contiene(testo: str, frammento: str) -> bool:
    return norm(frammento) in norm(testo)


def it(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def da_iso(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def giorni(dal: date, al: date):
    d = dal
    while d <= al:
        yield d
        d += timedelta(days=1)


def finestre(dal: date, al: date, ampiezza: int):
    d = dal
    while d <= al:
        fine = min(al, d + timedelta(days=ampiezza - 1))
        yield d, fine
        d = fine + timedelta(days=1)
