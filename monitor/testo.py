"""Estrazione del testo dai PDF: frontespizio (chi propone, quale struttura) e parte dispositiva."""
from __future__ import annotations

import io
import logging
import re

from pypdf import PdfReader

log = logging.getLogger(__name__)


def testo_pdf(dati: bytes, max_pagine: int = 40) -> list[str]:
    reader = PdfReader(io.BytesIO(dati))
    pagine = []
    for p in reader.pages[:max_pagine]:
        try:
            pagine.append(p.extract_text() or "")
        except Exception as e:  # noqa: BLE001 - un PDF malformato non deve fermare il giro
            log.info("pagina non leggibile: %s", e)
            pagine.append("")
    return pagine


# --------------------------------------------------------------------------
# Frontespizio
# --------------------------------------------------------------------------
RE_DIREZIONE = re.compile(r"\bDIREZIONE\s+[A-Z0-9 ,'’\.\-À-Ü]+")
RE_SETTORE = re.compile(r"^\s*SETTORE\s+(.+)$", re.M)
RE_HASH = re.compile(r"\b[0-9a-f]{64}\b")
ETICHETTE = r"(?:Proponente|Pubblicit|Dirigente\s+Responsabile|Direttore|Oggetto|Presenti|Assenti|STRUTTURE\s+INTERESSATE|ALLEGATI|Allegati|Denominazione|Struttura\s+Proponente|Dipartimento\s+Proponente|Responsabile\s+di\s+settore)"


def _pulisci(riga: str) -> str:
    return re.sub(r"\s+", " ", riga).strip(" :\t")


def _valore_dopo(etichetta: str, testo: str) -> str:
    m = re.search(etichetta + r"\s*:?[ \t]*([^\n]*)", testo)
    if not m:
        return ""
    v = _pulisci(m.group(1))
    if not v:  # valore sulla riga successiva
        resto = testo[m.end():].lstrip("\n")
        v = _pulisci(resto.split("\n", 1)[0])
    if re.match(ETICHETTE, v):
        return ""
    return v


def _blocco(inizio: str, testo: str, fine: str = ETICHETTE) -> list[str]:
    m = re.search(inizio + r"\s*:?", testo)
    if not m:
        return []
    resto = testo[m.end():]
    f = re.search(r"(?m)^\s*" + fine, resto)
    blocco = resto[: f.start()] if f else resto[:600]
    return [_pulisci(r) for r in blocco.split("\n") if _pulisci(r) and not RE_HASH.search(r)]


def _nome_persona(s: str) -> str:
    """Tiene solo la parte che sembra un nome (es. 'Lorenzo BACCI')."""
    s = re.split(r"\s{2,}|\t|Oggetto|Direttore|Pubblicit", s)[0]
    parole = [p for p in s.split() if re.match(r"^[A-Za-zÀ-ÿ'’\-]+$", p)]
    return " ".join(parole[:5])


def frontespizio(pagine: list[str]) -> dict:
    """Legge le etichette della prima pagina. Campi non trovati restano vuoti."""
    t = "\n".join(pagine[:2])
    fr: dict = {}

    # Atti di Giunta: "Proponente" seguito da assessori e direzione
    prop = _blocco(r"Proponente", t)
    if prop:
        fr["proponenti"] = [p for p in prop if not p.upper().startswith("DIREZIONE") and p.isupper()]
        fr["direzioni"] = [p for p in prop if p.upper().startswith("DIREZIONE")]
    fr["dirigente_responsabile"] = _nome_persona(_valore_dopo(r"Dirigente\s+Responsabile", t))
    fr["direttore"] = _nome_persona(_valore_dopo(r"(?<![A-Za-z])Direttore(?!\s+Generale)", t))

    strutt = _blocco(r"STRUTTURE\s+INTERESSATE", t,
                     fine=r"(?:Delibera|Decisione|Comunicazione|Proposta|Il presente|ALLEGATI|Allegati|LA GIUNTA)")
    if strutt:
        fr["strutture_interessate"] = [s for s in strutt if s.upper().startswith(("DIREZIONE", "SETTORE"))]

    # Decreti dirigenziali: "Responsabile di settore X" / "SETTORE ..." / "DIREZIONE ..."
    rs = _valore_dopo(r"Responsabile\s+di\s+settore", t)
    if rs:
        fr["responsabile_settore"] = _nome_persona(rs)
    ms = RE_SETTORE.search(t)
    if ms:
        fr["settore"] = _pulisci(ms.group(1))

    # Decreti del Presidente: "Struttura Proponente" / "Dipartimento Proponente"
    sp = _valore_dopo(r"Struttura\s+Proponente", t) or _valore_dopo(r"Dipartimento\s+Proponente", t)
    if sp:
        fr["struttura_proponente"] = sp

    if not fr.get("direzioni"):
        dz = [_pulisci(m.group(0)) for m in RE_DIREZIONE.finditer(t[:3000])]
        if dz:
            fr["direzioni"] = list(dict.fromkeys(dz))[:3]
    fr["testo_prima_pagina"] = t[:2500]
    return {k: v for k, v in fr.items() if v}


# --------------------------------------------------------------------------
# Parte dispositiva
# --------------------------------------------------------------------------
def _spaziata(parola: str) -> str:
    return r"\s?".join(parola)


VERBI = ["DELIBERA", "DECIDE", "DECRETA", "ORDINA", "DISPONE", "APPROVA"]
RE_INIZIO = re.compile(
    r"(?m)^[ \t]*(?:A\s+VOTI\s+UNANIMI\s*)?(?:" + "|".join(_spaziata(v) for v in VERBI) + r")[ \t]*:?[ \t]*$"
)
RE_INIZIO_INLINE = re.compile(r"(?:A\s+VOTI\s+UNANIMI|a\s+voti\s+unanimi)\s*\n?\s*(?:" +
                              "|".join(_spaziata(v) for v in VERBI) + r")\b")
RE_FINE = re.compile(
    r"(?m)^[ \t]*(?:IL\s+SEGRETARIO\s+DELLA\s+GIUNTA|Il\s+Segretario\s+della\s+Giunta|IL\s+DIRIGENTE|Il\s+Dirigente\b|"
    r"IL\s+DIRETTORE|Il\s+Direttore\b|IL\s+PRESIDENTE|Il\s+Presidente\b|Il\s+presente\s+atto\s+(?:e'?|è)\s+pubblicato|"
    r"Allegati\s*$|ALLEGATI\s*$|Firmato\s+digitalmente)"
)
RE_RUMORE = re.compile(
    r"(?m)^\s*(?:\d{1,4}|.*Bollettino Ufficiale della Regione Toscana.*|[0-9a-f]{64}|pag\.\s*\d+.*)\s*$"
)


def dispositivo(pagine: list[str], max_car: int = 8000) -> str:
    t = "\n".join(pagine)
    m = RE_INIZIO.search(t) or RE_INIZIO_INLINE.search(t)
    if not m:
        return ""
    corpo = t[m.end():]
    f = RE_FINE.search(corpo)
    if f:
        corpo = corpo[: f.start()]
    corpo = RE_RUMORE.sub("", corpo)
    corpo = re.sub(r"[ \t]+", " ", corpo)
    corpo = re.sub(r"\n{3,}", "\n\n", corpo).strip()
    verbo = re.sub(r"\s", "", m.group(0)).replace("AVOTIUNANIMI", "").strip(":")
    testo = f"{verbo}\n{corpo}"
    return testo if len(testo) <= max_car else testo[:max_car].rsplit(" ", 1)[0] + " […]"
