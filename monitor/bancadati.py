"""Client della Banca dati degli atti della Giunta regionale toscana.

Endpoint verificati (novembre 2026) - sono quelli usati dalla pagina
https://www.regione.toscana.it/ricerca-atti :
  POST RicercaAttiG.json  (atti di Giunta)       parametri: dataDal, dataAl, id_proponente (assessore), tipologia, oggetto
  POST RicercaAttiP.json  (atti del Presidente)  parametri: dataDal, dataAl
  POST RicercaAttiD.json  (decreti dirigenziali) parametri: dataDal, dataAl, id_dirigente
  GET  DettaglioAtti{G,P,D}.json?codprat=...     scheda con allegati
  GET  Contenuto.xml?id=...                      PDF dell'atto / dell'allegato
  POST getDirigenti.json / getProponenti.json    elenchi per i filtri
Ogni ricerca restituisce AL MASSIMO 200 risultati: le finestre vengono
ristrette automaticamente fino a scendere sotto il limite.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta

import requests

from .util import finestre, giorni, it

log = logging.getLogger(__name__)

BASE = "https://www301.regione.toscana.it/bancadati/atti/"
LIMITE = 200
FONTI = {"G": "RicercaAttiG", "P": "RicercaAttiP", "D": "RicercaAttiD"}


class BancaDati:
    def __init__(self, pausa: float = 0.25, tentativi: int = 4):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "monitor-atti-quinta-commissione/1.0 (consultazione atti pubblici)",
            "Accept": "application/json, text/xml, application/pdf, */*",
        })
        self.pausa = pausa
        self.tentativi = tentativi
        self.avvisi: list[str] = []

    # --- HTTP -------------------------------------------------------------
    def _req(self, metodo: str, url: str, **kw) -> requests.Response:
        ultimo = None
        for i in range(self.tentativi):
            try:
                r = self.s.request(metodo, url, timeout=60, **kw)
                if r.status_code == 200:
                    time.sleep(self.pausa)
                    return r
                ultimo = f"HTTP {r.status_code}"
            except requests.RequestException as e:  # rete, timeout
                ultimo = str(e)
            time.sleep(2 * (i + 1))
        raise RuntimeError(f"{metodo} {url} fallita: {ultimo}")

    def _json(self, r: requests.Response) -> dict:
        return json.loads(r.content.decode("utf-8", errors="replace"), strict=False)

    def _post(self, endpoint: str, params: dict | None = None) -> dict:
        r = self._req(
            "POST", BASE + endpoint,
            data=params or None,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        return self._json(r)

    # --- ricerche ---------------------------------------------------------
    def ricerca(self, fonte: str, dal: date, al: date, **filtri) -> list[dict]:
        nome = FONTI[fonte]
        params = {"dataDal": it(dal), "dataAl": it(al), **filtri}
        dati = self._post(nome + ".json", params)
        atti = (dati.get(nome) or {}).get("atto") or []
        for a in atti:
            a["_fonte"] = fonte
        return atti

    def ricerca_completa(self, fonte: str, dal: date, al: date, **filtri) -> list[dict]:
        """Come ricerca(), ma divide la finestra finche' i risultati sono < 200."""
        atti = self.ricerca(fonte, dal, al, **filtri)
        if len(atti) < LIMITE:
            return atti
        if dal == al:
            msg = (f"Ricerca {fonte} del {it(dal)} {filtri or ''} ha restituito {LIMITE} risultati "
                   f"(limite della banca dati): possibile troncamento, coperto dalle ricerche per dirigente.")
            log.warning(msg)
            self.avvisi.append(msg)
            return atti
        meta = dal + timedelta(days=(al - dal).days // 2)
        return (self.ricerca_completa(fonte, dal, meta, **filtri)
                + self.ricerca_completa(fonte, meta + timedelta(days=1), al, **filtri))

    def elenco(self, fonte: str, dal: date, al: date, ampiezza: int = 7, **filtri) -> list[dict]:
        visti, out = set(), []
        for a, b in finestre(dal, al, ampiezza):
            for atto in self.ricerca_completa(fonte, a, b, **filtri):
                if atto["CODICE"] not in visti:
                    visti.add(atto["CODICE"])
                    out.append(atto)
        return out

    def decreti_per_giorno(self, dal: date, al: date) -> list[dict]:
        out = []
        for g in giorni(dal, al):
            out += self.ricerca_completa("D", g, g)
        return out

    # --- elenchi ----------------------------------------------------------
    def dirigenti(self) -> list[dict]:
        return self._post("getDirigenti.json")["getDirigenti"]["Dirigente"]

    def assessori(self) -> list[dict]:
        return self._post("getProponenti.json")["getProponenti"]["Proponente"]

    # --- singolo atto -----------------------------------------------------
    def dettaglio(self, fonte: str, codice: str) -> dict:
        nome = f"DettaglioAtti{fonte}"
        for url in (f"{BASE}{nome}.json?codprat={codice}",
                    f"https://www301.regione.toscana.it/bancadati/traspamm/atti/{nome}.json?codprat={codice}"):
            try:
                d = self._json(self._req("GET", url))
                atto = (d.get(nome) or {}).get("atto") or []
                if atto:
                    return atto[0]
            except Exception as e:  # noqa: BLE001
                log.info("dettaglio %s non disponibile su %s: %s", codice, url, e)
        return {}

    def pdf(self, id_contenuto: str) -> bytes:
        r = self._req("GET", url_pdf(id_contenuto))
        if not r.content.startswith(b"%PDF"):
            raise RuntimeError(f"Contenuto {id_contenuto} non e' un PDF")
        return r.content


def url_pdf(id_contenuto: str) -> str:
    return f"{BASE}Contenuto.xml?id={id_contenuto}"


def url_scheda(fonte: str, codice: str) -> str:
    return f"{BASE}DettaglioAtti{fonte}.xml?codprat={codice}"
