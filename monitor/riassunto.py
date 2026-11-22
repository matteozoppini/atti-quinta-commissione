"""Riassunto breve dell'atto.

Se e' impostato il segreto ANTHROPIC_API_KEY il riassunto e' scritto da Claude
(3-4 righe, solo sui fatti del testo). Altrimenti si usa un riassunto automatico
estrattivo: oggetto + primo punto del dispositivo.
"""
from __future__ import annotations

import logging
import os
import re

import requests

log = logging.getLogger(__name__)
MODELLO = os.environ.get("MODELLO_RIASSUNTI", "claude-haiku-5-5")

PROMPT = """Sei un funzionario del Consiglio regionale della Toscana. Riassumi in italiano, in massimo 3 frasi brevi \
(massimo 60 parole in tutto), cosa stabilisce questo atto: cosa si decide, a favore di chi, importi e scadenze se presenti. \
Usa solo informazioni presenti nel testo, senza commenti e senza premesse.

TIPO: {tipo}
OGGETTO: {oggetto}

PARTE DISPOSITIVA:
{dispositivo}

INIZIO DELL'ATTO (premesse):
{premesse}"""


def automatico(oggetto: str, dispositivo: str) -> str:
    primo = ""
    if dispositivo:
        corpo = dispositivo.split("\n", 1)[1] if "\n" in dispositivo else dispositivo
        punti = [p.strip() for p in re.split(r"\n\s*(?=\d+\s*[\)\.\-–])", corpo.strip()) if p.strip()]
        primo = re.sub(r"\s+", " ", punti[0] if punti else corpo)
        primo = re.sub(r"^\d+\s*[\)\.\-–]\s*", "", primo).rstrip(";")
        if len(primo) > 320:
            primo = primo[:320].rsplit(" ", 1)[0] + "…"
    return f"{oggetto.strip()}" + (f" — Dispone: {primo}" if primo else "")


def riassumi(tipo: str, oggetto: str, dispositivo: str, premesse: str) -> tuple[str, bool]:
    """Restituisce (testo, scritto_da_IA)."""
    chiave = os.environ.get("ANTHROPIC_API_KEY")
    if not chiave or not (dispositivo or premesse):
        return automatico(oggetto, dispositivo), False
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": chiave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": MODELLO,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": PROMPT.format(
                    tipo=tipo, oggetto=oggetto, dispositivo=dispositivo[:5000], premesse=premesse[:3000])}],
            },
            timeout=90,
        )
        r.raise_for_status()
        testo = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        if testo:
            return testo, True
    except Exception as e:  # noqa: BLE001 - in caso di errore si ripiega sul riassunto automatico
        log.warning("riassunto IA non riuscito: %s", e)
    return automatico(oggetto, dispositivo), False
