"""Regole strutturali di appartenenza al perimetro della V Commissione.

Esito: 'pertinente' | 'verifica' | 'escluso', sempre con l'elenco dei motivi.
Principio: nel dubbio 'verifica' (incluso e segnalato), mai 'escluso'.
"""
from __future__ import annotations

from .organigramma import Indice
from .util import chiave_persona, contiene, norm

ORDINE = {"escluso": 0, "verifica": 1, "pertinente": 2}


class Esito:
    def __init__(self):
        self.stato = "escluso"
        self.motivi: list[str] = []
        self.temi: list[str] = []
        self.settore: str = ""
        self.principale: str = ""

    def alza(self, stato: str, motivo: str, tema: str | None = None):
        if ORDINE[stato] > ORDINE[self.stato]:
            self.stato = stato
            self.principale = motivo
        self.motivi.append(motivo)
        if tema and tema not in self.temi:
            self.temi.append(tema)

    def nota(self, motivo: str):
        self.motivi.append(motivo)

    def dict(self):
        principale = self.principale or (self.motivi[0] if self.motivi else "")
        altri = [m for m in self.motivi if m != principale]
        return {"stato": self.stato, "motivi": ([principale] if principale else []) + altri,
                "temi": self.temi, "settore": self.settore}


class Classificatore:
    def __init__(self, perimetro: dict, indice: Indice):
        self.p = perimetro
        self.ix = indice

    # --- utilita' ---------------------------------------------------------
    def stato_settore(self, cod: str) -> tuple[str, str]:
        if cod in self.p["settori"]:
            s = self.p["settori"][cod]
            return s["stato"], s["tema"]
        sett = self.ix.org["settori"].get(cod)
        if sett and sett["direzione"] in self.p["direzioni"]:
            nuovo = self.p["direzioni"][sett["direzione"]].get("nuovi_settori", "escluso")
            if nuovo != "escluso" and cod not in self.p.get("settori_esclusi", {}):
                return nuovo, "Settore nuovo o non classificato"
        return "escluso", ""

    def stato_direttore(self, cod_dir: str) -> str:
        d = self.p["direzioni"].get(cod_dir)
        return d["direttore"] if d else "escluso"

    def direzione_di_ufficio(self, ufficio: str) -> str | None:
        for cod, d in self.p["direzioni"].items():
            if contiene(ufficio, d["ufficio_bd"]):
                return cod
        return None

    def valuta_persona(self, e: Esito, persona: str, ruolo: str):
        """Applica gli incarichi della persona (dirigente di settore o direttore)."""
        inc = self.ix.incarichi(persona)
        if not inc:
            return False
        dentro = [i for i in inc if (i["tipo"] == "settore" and self.stato_settore(i["codice"])[0] != "escluso")
                  or (i["tipo"] == "direttore" and self.stato_direttore(i["codice"]) != "escluso")]
        fuori = [i for i in inc if i not in dentro]
        for i in dentro:
            if i["tipo"] == "settore":
                st, tema = self.stato_settore(i["codice"])
                if fuori:  # la persona guida anche strutture fuori perimetro
                    st = "verifica"
                e.alza(st, f"{ruolo} {persona}: responsabile del settore {self.ix.nome_settore(i['codice'])}"
                           + (" (guida anche settori fuori perimetro)" if fuori else ""), tema)
                e.settore = e.settore or self.ix.nome_settore(i["codice"])
            else:
                st = self.stato_direttore(i["codice"])
                e.alza(st, f"{ruolo} {persona}: direttore della direzione {self.p['direzioni'][i['codice']]['nome']}"
                           + (" (direzione con competenze miste)" if st == "verifica" else ""))
        if not dentro:
            nomi = ", ".join(self.ix.nome_settore(i["codice"]) if i["tipo"] == "settore"
                             else "direzione " + i["codice"] for i in fuori)
            e.nota(f"{ruolo} {persona}: incarichi fuori perimetro ({nomi})")
        return True

    # --- atti di Giunta ---------------------------------------------------
    def giunta(self, atto: dict, fr: dict) -> Esito:
        e = Esito()
        letto = bool(fr.get("dirigente_responsabile") or fr.get("proponenti"))
        dr = fr.get("dirigente_responsabile", "")
        if dr and not self.valuta_persona(e, dr, "Dirigente responsabile"):
            e.alza("verifica", f"Dirigente responsabile {dr} non trovato nell'organigramma attuale")

        direzioni = fr.get("direzioni") or [atto.get("UFFICIO", "")]
        for dz in direzioni:
            cod = self.direzione_di_ufficio(dz)
            if cod == "50124":
                e.alza("pertinente", f"Direzione proponente: {dz}", "Cultura")
            elif cod == "50125" and not dr:
                e.alza("verifica", f"Direzione proponente: {dz} (dirigente non letto)")

        for s in fr.get("strutture_interessate", []):
            for frag in self.p["giunta_strutture_interessate"]["pertinente"]:
                if contiene(s, frag):
                    e.alza("pertinente", f"Struttura interessata: {s}")
            for frag in self.p["giunta_strutture_interessate"]["verifica"]:
                if contiene(s, frag) and e.stato == "escluso":
                    e.alza("verifica", f"Struttura interessata: {s} (direzione con competenze miste)")

        segnalati = {chiave_persona(a) for a in self.p["assessori_segnalati"]}
        for a in fr.get("proponenti", []):
            if chiave_persona(a) in segnalati and e.stato == "escluso":
                e.alza("verifica", f"Proponente: assessore {a.title()} (deleghe anche in materie della Commissione)")

        if not letto:
            e.alza("verifica", "Frontespizio non leggibile: controllo manuale")
        if e.stato == "escluso" and not e.motivi:
            e.nota("Nessun legame con le strutture del perimetro")
        return e

    # --- decreti del Presidente -------------------------------------------
    def presidente(self, atto: dict, fr: dict) -> Esito:
        e = Esito()
        struttura = fr.get("struttura_proponente") or atto.get("UFFICIO", "")
        for frag in self.p["presidente_strutture"]["pertinente"]:
            if contiene(struttura, frag):
                e.alza("pertinente", f"Struttura proponente: {struttura}", "Cultura")
        for frag in self.p["presidente_strutture"]["verifica"]:
            if contiene(struttura, frag) and e.stato == "escluso":
                e.alza("verifica", f"Struttura proponente: {struttura} (competenze trasversali o miste)")
        if not struttura:
            e.alza("verifica", "Struttura proponente non leggibile: controllo manuale")
        if e.stato == "escluso":
            e.nota(f"Struttura proponente fuori perimetro: {struttura}")
        return e

    # --- decreti dirigenziali ---------------------------------------------
    def dirigenti(self, atto: dict, fr: dict) -> Esito:
        e = Esito()
        cod = self.ix.settore_da_nome(fr.get("settore", ""))
        if cod:
            st, tema = self.stato_settore(cod)
            e.settore = self.ix.nome_settore(cod)
            if st != "escluso":
                e.alza(st, f"Settore: {e.settore}" + (" (competenze miste)" if st == "verifica" else ""), tema)
            else:
                e.nota(f"Settore fuori perimetro: {e.settore}")
            return e
        if fr.get("settore"):
            e.alza("verifica", f"Settore '{fr['settore']}' non presente nell'organigramma attuale")
        resp = fr.get("responsabile_settore") or fr.get("direttore")
        if resp:
            if not self.valuta_persona(e, resp, "Firmatario"):
                e.alza("verifica", f"Firmatario {resp} non trovato nell'organigramma attuale")
        if not fr.get("settore") and not resp:
            dir_cod = self.direzione_di_ufficio(atto.get("UFFICIO", ""))
            if dir_cod:
                e.alza("verifica", f"Frontespizio non leggibile (direzione {atto.get('UFFICIO')}): controllo manuale")
        if e.stato == "escluso" and not e.motivi:
            e.nota("Nessun legame con le strutture del perimetro")
        return e

    def classifica(self, atto: dict, fr: dict) -> Esito:
        return {"G": self.giunta, "P": self.presidente, "D": self.dirigenti}[atto["_fonte"]](atto, fr)


def candidato_decreto(atto: dict, perimetro: dict) -> bool:
    """Un decreto va esaminato (PDF scaricato) se viene da una direzione del perimetro."""
    return any(contiene(atto.get("UFFICIO", ""), d["ufficio_bd"]) for d in perimetro["direzioni"].values())


def segnalato(nome: str, perimetro: dict) -> bool:
    return chiave_persona(nome) in {chiave_persona(a) for a in perimetro["assessori_segnalati"]}


__all__ = ["Classificatore", "Esito", "candidato_decreto", "norm"]
