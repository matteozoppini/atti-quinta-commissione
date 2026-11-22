"""Archivio su file JSON (cartella docs/data, pubblicata con la pagina web)."""
from __future__ import annotations

import json
from pathlib import Path

MAX_TENTATIVI = 5
VERSIONE_REGOLE = 2  # aumentandola, gli atti gia' in archivio vengono riletti e riclassificati (senza notifica)


class Archivio:
    def __init__(self, cartella: Path):
        self.dir = cartella
        self.dir.mkdir(parents=True, exist_ok=True)
        self.atti: dict[str, dict] = {}
        for f in sorted(self.dir.glob("atti-*.json")):
            for a in json.loads(f.read_text(encoding="utf-8")):
                self.atti[a["codice"]] = a

    def leggi(self, nome: str, default):
        f = self.dir / nome
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default

    def scrivi(self, nome: str, dati) -> None:
        (self.dir / nome).write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")

    def da_elaborare(self, codice: str) -> bool:
        a = self.atti.get(codice)
        return (a is None or a.get("versione", 1) < VERSIONE_REGOLE
                or (a.get("errore") and a.get("tentativi", 0) < MAX_TENTATIVI))

    def metti(self, rec: dict) -> None:
        rec["versione"] = VERSIONE_REGOLE
        vecchio = self.atti.get(rec["codice"])
        if vecchio:
            rec["prima_vista"] = vecchio.get("prima_vista", rec.get("prima_vista"))
            rec["tentativi"] = vecchio.get("tentativi", 0) + 1
        self.atti[rec["codice"]] = rec

    def salva(self) -> list[int]:
        per_anno: dict[int, list] = {}
        for a in self.atti.values():
            per_anno.setdefault(int(a["data"][:4]), []).append(a)
        for anno, lista in per_anno.items():
            lista.sort(key=lambda x: (x["data"], x["fonte"], int(x["numero"]) if str(x["numero"]).isdigit() else 0),
                       reverse=True)
            (self.dir / f"atti-{anno}.json").write_text(
                json.dumps(lista, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return sorted(per_anno, reverse=True)
