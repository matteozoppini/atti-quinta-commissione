"""Organigramma della Giunta regionale (banca dati uffici) e confronto nel tempo.

Fonte: https://www301.regione.toscana.it/bancadati/uffici/Strutture.xml?cmu=<codice>
Per ogni direzione restituisce il direttore e le strutture figlie (settori);
per ogni settore restituisce il responsabile (dirigente) e l'atto di incarico.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET

import requests

from .util import chiave_persona, norm, norm_settore

log = logging.getLogger(__name__)
URL = "https://www301.regione.toscana.it/bancadati/uffici/Strutture.xml?cmu={}"


def _t(nodo, percorso: str) -> str:
    e = nodo.find(percorso) if nodo is not None else None
    return (e.text or "").strip() if e is not None and e.text else ""


def analizza_xml(xml: str) -> dict:
    root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    inc = root.find("incaricato")
    figli = []
    for f in root.findall("strutturafiglio"):
        figli.append({"codice": _t(f, "CODICE"), "nome": _t(f, "NOME"), "tipo": _t(f, "TIPO")})
    responsabile = (f"{_t(inc, 'COGNOME')} {_t(inc, 'NOME')}").strip()
    return {
        "nome": _t(root, "struttura/NOME"),
        "ruolo": _t(inc, "DESCRIZIONE"),
        "responsabile": responsabile,
        "incarico": _t(inc, "ATTO_DESCR"),
        "figli": figli,
    }


def scarica(direzioni: list[str], pausa: float = 0.1) -> dict:
    """Restituisce {'direzioni': {cod: {...}}, 'settori': {cod: {...}}}."""
    s = requests.Session()
    s.headers["User-Agent"] = "monitor-atti-quinta-commissione/1.0"

    def get(cod):
        for i in range(4):
            try:
                r = s.get(URL.format(cod), timeout=60)
                if r.status_code == 200:
                    time.sleep(pausa)
                    return analizza_xml(r.content.decode("utf-8", errors="replace"))
            except (requests.RequestException, ET.ParseError) as e:
                log.info("organigramma %s: %s", cod, e)
            time.sleep(2 * (i + 1))
        raise RuntimeError(f"organigramma: struttura {cod} non leggibile")

    org = {"direzioni": {}, "settori": {}}
    for d in direzioni:
        x = get(d)
        org["direzioni"][d] = {"nome": x["nome"], "direttore": x["responsabile"], "ruolo": x["ruolo"]}
        for f in x["figli"]:
            if f["tipo"] != "SETTORE":
                continue
            y = get(f["codice"])
            org["settori"][f["codice"]] = {
                "nome": f["nome"], "direzione": d,
                "responsabile": y["responsabile"], "incarico": y["incarico"],
            }
    return org


class Indice:
    """Ricerche veloci su un organigramma: persona -> incarichi, nome settore -> codice."""

    def __init__(self, org: dict):
        self.org = org
        self.per_persona: dict[str, list[dict]] = {}
        self.per_nome_settore: dict[str, str] = {}
        for cod, s in org["settori"].items():
            self.per_nome_settore[norm_settore(s["nome"])] = cod
            if s["responsabile"]:
                self.per_persona.setdefault(chiave_persona(s["responsabile"]), []).append(
                    {"tipo": "settore", "codice": cod, "direzione": s["direzione"]})
        for cod, d in org["direzioni"].items():
            if d["direttore"]:
                self.per_persona.setdefault(chiave_persona(d["direttore"]), []).append(
                    {"tipo": "direttore", "codice": cod, "direzione": cod})

    def incarichi(self, persona: str) -> list[dict]:
        return self.per_persona.get(chiave_persona(persona), []) if persona else []

    def settore_da_nome(self, nome: str) -> str | None:
        if not nome:
            return None
        n = norm_settore(nome)
        if n in self.per_nome_settore:
            return self.per_nome_settore[n]
        # nomi troncati o con piccole differenze: confronto sui primi 45 caratteri
        for k, cod in self.per_nome_settore.items():
            if len(n) >= 15 and (k.startswith(n[:45]) or n.startswith(k[:45])):
                return cod
        return None

    def nome_settore(self, cod: str) -> str:
        s = self.org["settori"].get(cod)
        return s["nome"] if s else cod


def confronta(vecchio: dict | None, nuovo: dict, perimetro: dict) -> list[str]:
    """Cambiamenti rilevanti per il perimetro (dirigenti, settori nuovi o soppressi)."""
    if not vecchio:
        return []
    avvisi = []
    dir_perim = perimetro["direzioni"]
    for cod in perimetro["settori"]:
        v, n = vecchio["settori"].get(cod), nuovo["settori"].get(cod)
        if v and not n:
            avvisi.append(f"Il settore del perimetro {cod} ({v['nome']}) non compare piu' nell'organigramma: "
                          f"aggiornare perimetro.json.")
        elif n and v and norm(v["responsabile"]) != norm(n["responsabile"]):
            avvisi.append(f"Cambio di responsabile nel settore {n['nome']}: {v['responsabile'] or 'vacante'} -> "
                          f"{n['responsabile'] or 'vacante'} ({n['incarico']}).")
    for cod, n in nuovo["settori"].items():
        if cod not in vecchio["settori"] and n["direzione"] in dir_perim:
            avvisi.append(f"Nuovo settore nella direzione {dir_perim[n['direzione']]['nome']}: {n['nome']} "
                          f"(resp. {n['responsabile'] or 'vacante'}). Incluso in automatico come 'da verificare'.")
    for cod in dir_perim:
        v, n = vecchio["direzioni"].get(cod), nuovo["direzioni"].get(cod)
        if v and n and norm(v["direttore"]) != norm(n["direttore"]):
            avvisi.append(f"Cambio di direttore ({dir_perim[cod]['nome']}): {v['direttore']} -> {n['direttore']}.")
    return avvisi
