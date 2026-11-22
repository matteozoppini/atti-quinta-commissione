"""Giro di controllo: raccoglie gli atti nuovi, li classifica, aggiorna l'archivio e notifica.

Uso:
  python -m monitor.run                     # controllo ordinario (ultimi 20 giorni)
  python -m monitor.run --dal 2025-11-10    # archivio iniziale (riprende da solo nei giri successivi)
  python -m monitor.run --no-notifica
  python -m monitor.run --telegram-test     # trova il chat id e manda un messaggio di prova
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import organigramma, telegram
from .archivio import Archivio
from .bancadati import BancaDati, url_pdf, url_scheda
from .classifica import Classificatore, candidato_decreto
from .riassunto import riassumi
from .testo import dispositivo, frontespizio, testo_pdf
from .util import chiave_persona, da_iso

log = logging.getLogger("monitor")
RADICE = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Rome")
FINESTRA_GIORNI = 20  # la banca dati pubblica gli atti con qualche giorno di ritardo


def persone_del_perimetro(per: dict, org: dict) -> list[str]:
    persone = []
    for cod in per["settori"]:
        s = org["settori"].get(cod)
        if s and s["responsabile"]:
            persone.append(s["responsabile"])
    for cod, d in per["direzioni"].items():
        if d["direttore"] != "escluso" and org["direzioni"].get(cod, {}).get("direttore"):
            persone.append(org["direzioni"][cod]["direttore"])
    for cod, s in org["settori"].items():  # settori nuovi delle direzioni del perimetro
        if (s["direzione"] in per["direzioni"] and cod not in per["settori"]
                and cod not in per.get("settori_esclusi", {})
                and per["direzioni"][s["direzione"]].get("nuovi_settori") != "escluso" and s["responsabile"]):
            persone.append(s["responsabile"])
    return list(dict.fromkeys(persone))


def base_record(a: dict) -> dict:
    tipo, _, resto = a["ATTO"].partition(" n.")
    return {
        "codice": a["CODICE"], "fonte": a["_fonte"], "tipo": tipo.strip(), "numero": a.get("NUMERO", ""),
        "data": a.get("DATA_ATTO", ""), "atto": a["ATTO"], "oggetto": (a.get("OGGETTO") or "").strip(),
        "ufficio": (a.get("UFFICIO") or "").strip(), "pubblicazione": a.get("TIPO_PUB", ""),
        "id_contenuto": a.get("ID_CONTENUTO", ""), "url_pdf": url_pdf(a.get("ID_CONTENUTO", "")),
        "url_scheda": url_scheda(a["_fonte"], a["CODICE"]),
    }


def elabora(a: dict, bd: BancaDati, cls: Classificatore, ora: str) -> dict:
    rec = base_record(a)
    rec["prima_vista"] = ora
    fr, pagine, errore = {}, [], None
    try:
        pagine = testo_pdf(bd.pdf(rec["id_contenuto"]))
        fr = frontespizio(pagine)
    except Exception as e:  # noqa: BLE001
        errore = str(e)[:200]
    esito = cls.classifica(a, fr)
    if errore:
        esito.stato = "verifica" if esito.stato == "escluso" else esito.stato
        esito.principale = f"PDF non scaricato o non leggibile ({errore}): nuovo tentativo al prossimo controllo"
        esito.motivi.insert(0, esito.principale)
        rec["errore"] = True
    rec.update(esito.dict())
    rec["frontespizio"] = {k: v for k, v in fr.items() if k != "testo_prima_pagina"}
    if not (fr.get("dirigente_responsabile") or fr.get("settore") or fr.get("struttura_proponente")
            or fr.get("responsabile_settore")) and fr.get("testo_prima_pagina"):
        rec["frontespizio_grezzo"] = fr["testo_prima_pagina"][:1500]

    if rec["stato"] != "escluso":
        rec["dispositivo"] = dispositivo(pagine) if pagine else ""
        premesse = "\n".join(pagine[:3])[:3000]
        rec["riassunto"], rec["riassunto_ia"] = riassumi(rec["tipo"], rec["oggetto"], rec["dispositivo"], premesse)
        try:
            det = bd.dettaglio(rec["fonte"], rec["codice"])
            rec["allegati"] = [{"descrizione": x.get("DESCRIZIONE", "").strip(), "url": url_pdf(x["ID_CONTENUTO"])}
                               for x in det.get("ALLEGATO", []) if x.get("ID_CONTENUTO")]
        except Exception as e:  # noqa: BLE001
            log.info("allegati %s: %s", rec["codice"], e)
            rec["allegati"] = []
    return rec


def invia_riepilogo_richiesto() -> None:
    """Se esiste richieste/riepilogo.json ({"dal": "AAAA-MM-GG", "al": opzionale}) invia su Telegram
    il riepilogo degli atti inclusi (pertinenti e da verificare) gia' presenti in archivio."""
    f = RADICE / "richieste" / "riepilogo.json"
    if not f.exists():
        return
    req = json.loads(f.read_text(encoding="utf-8"))
    dal, al = req["dal"], req.get("al") or datetime.now(TZ).date().isoformat()
    arch = Archivio(RADICE / "docs" / "data")
    atti = [a for a in arch.atti.values() if a["stato"] != "escluso" and dal <= a["data"] <= al]
    sito = os.environ.get("SITO_URL") or "https://matteozoppini.github.io/atti-quinta-commissione/"
    msg = telegram.componi_riepilogo(atti, dal, al, sito.rstrip("/") + "/")
    print(f"Riepilogo dal {dal} al {al}: {len(atti)} atti in {len(msg)} messaggi")
    telegram.invia(msg)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dal", help="data iniziale AAAA-MM-GG (archivio iniziale)")
    ap.add_argument("--no-notifica", action="store_true")
    ap.add_argument("--max-nuovi", type=int, default=int(os.environ.get("MAX_NUOVI", 700)))
    ap.add_argument("--minuti", type=int, default=int(os.environ.get("MINUTI_MAX", 300)))
    ap.add_argument("--telegram-test", action="store_true")
    ap.add_argument("--prova", nargs="*", help="ID_CONTENUTO di PDF reali: stampa frontespizio e dispositivo letti")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.telegram_test:
        telegram.trova_chat()
        invia_riepilogo_richiesto()
        return 0
    if args.prova is not None:
        bd = BancaDati()
        for i in args.prova or ["5537087", "5537167", "5538974", "5533942", "5535131"]:
            pagine = testo_pdf(bd.pdf(i))
            fr = frontespizio(pagine)
            grezzo = fr.pop("testo_prima_pagina", "")
            print(f"\n===== {i} =====\n--- testo prima pagina ---\n{grezzo[:1200]}\n--- campi letti ---")
            print(json.dumps(fr, ensure_ascii=False, indent=1))
            print("--- dispositivo ---\n" + dispositivo(pagine)[:800])
        return 0

    t0 = time.time()
    per = json.loads((RADICE / "perimetro.json").read_text(encoding="utf-8"))
    arch = Archivio(RADICE / "docs" / "data")
    stato = arch.leggi("stato.json", {})
    indice = arch.leggi("indice.json", {})
    adesso = datetime.now(TZ)
    oggi = adesso.date()
    ora = adesso.isoformat(timespec="minutes")
    sito = os.environ.get("SITO_URL", "").rstrip("/") + "/"

    if args.dal:
        stato["recupero_dal"] = args.dal
    dal = oggi - timedelta(days=FINESTRA_GIORNI)
    if stato.get("recupero_dal"):
        dal = min(dal, da_iso(stato["recupero_dal"]))
    log.info("Controllo dal %s al %s", dal, oggi)

    # 1. organigramma
    avvisi: list[str] = []
    vecchio_org = arch.leggi("organigramma.json", None)
    try:
        org = organigramma.scarica(per["tutte_le_direzioni"])
        avvisi += organigramma.confronta(vecchio_org, org, per)
        org["aggiornato"] = ora
        arch.scrivi("organigramma.json", org)
    except Exception as e:  # noqa: BLE001
        if not vecchio_org:
            raise
        org = vecchio_org
        avvisi.append(f"Organigramma non aggiornato in questo controllo ({e}): uso la versione del {org.get('aggiornato')}.")
    cls = Classificatore(per, organigramma.Indice(org))

    # 2. elenchi dalla banca dati
    bd = BancaDati()
    giunta = bd.elenco("G", dal, oggi, ampiezza=7)
    presidente = bd.elenco("P", dal, oggi, ampiezza=15)
    tutti_decreti = bd.decreti_per_giorno(dal, oggi)
    decreti = {a["CODICE"]: a for a in tutti_decreti if candidato_decreto(a, per)}

    # 2b. ricerche per dirigente (controllo indipendente)
    elenco_dir: dict[str, list[str]] = {}
    for d in bd.dirigenti():
        elenco_dir.setdefault(chiave_persona(d["NOME"]), []).append(d["ID"])
    da_dirigente = 0
    for persona in persone_del_perimetro(per, org):
        ids = elenco_dir.get(chiave_persona(persona))
        if not ids:
            avvisi.append(f"{persona} (perimetro) non e' nell'elenco dirigenti della banca dati atti: "
                          f"i suoi decreti sono coperti solo dalla scansione giornaliera.")
            continue
        for i in ids:
            for a in bd.elenco("D", dal, oggi, ampiezza=31, id_dirigente=i):
                if a["CODICE"] not in decreti:
                    da_dirigente += 1
                decreti[a["CODICE"]] = a
    avvisi += bd.avvisi

    candidati = giunta + presidente + list(decreti.values())
    nuovi = [a for a in candidati if arch.da_elaborare(a["CODICE"])]
    nuovi.sort(key=lambda a: a.get("DATA_ATTO", ""), reverse=True)
    log.info("Giunta %d, Presidente %d, decreti %d (di cui candidati %d, +%d solo da ricerca per dirigente); da elaborare %d",
             len(giunta), len(presidente), len(tutti_decreti), len(decreti), da_dirigente, len(nuovi))

    # 3. elaborazione
    elaborati, interrotto = [], False
    for n, a in enumerate(nuovi):
        if n >= args.max_nuovi or (time.time() - t0) > args.minuti * 60:
            interrotto = True
            break
        prima_volta = a["CODICE"] not in arch.atti
        rec = elabora(a, bd, cls, ora)
        arch.metti(rec)
        if prima_volta:
            elaborati.append(rec)
        if n % 25 == 0:
            log.info("  %d/%d %s -> %s", n + 1, len(nuovi), rec["atto"], rec["stato"])
            arch.salva()  # salvataggi intermedi: un'interruzione non perde il lavoro fatto

    if stato.get("recupero_dal") and not interrotto:
        log.info("Archivio iniziale completato dal %s", stato["recupero_dal"])
        stato.pop("recupero_dal")
    if interrotto:
        avvisi.append(f"Elaborati {len(elaborati)} atti su {len(nuovi)}: il resto verra' completato nei prossimi controlli.")

    anni = arch.salva()
    rilevanti = [r for r in elaborati if r["stato"] != "escluso"]
    controllo = {
        "quando": ora, "dal": dal.isoformat(), "al": oggi.isoformat(),
        "giunta": len(giunta), "presidente": len(presidente),
        "decreti_totali": len(tutti_decreti), "decreti_esaminati": len(decreti),
        "nuovi": len(elaborati), "pertinenti": sum(r["stato"] == "pertinente" for r in elaborati),
        "verifica": sum(r["stato"] == "verifica" for r in elaborati),
        "esclusi": sum(r["stato"] == "escluso" for r in elaborati),
    }
    vecchi_avvisi = indice.get("avvisi", [])
    gia = {x["testo"] for x in vecchi_avvisi}
    avvisi_nuovi = [x for x in dict.fromkeys(avvisi) if x not in gia]
    indice.update({
        "commissione": per["commissione"], "aggiornato": ora, "anni": anni, "controllo": controllo,
        "novita": [r["codice"] for r in rilevanti] or indice.get("novita", []),
        "novita_quando": ora if rilevanti else indice.get("novita_quando"),
        "avvisi": ([{"quando": ora, "testo": x} for x in avvisi_nuovi] + vecchi_avvisi)[:60],
        "storico": ([controllo] + indice.get("storico", []))[:60],
        "perimetro": {"settori": per["settori"], "direzioni": per["direzioni"],
                      "assessori_segnalati": per["assessori_segnalati"]},
    })
    arch.scrivi("indice.json", indice)
    arch.scrivi("stato.json", stato)

    # 4. notifica solo se ci sono novita'
    if not args.no_notifica and (rilevanti or avvisi_nuovi):
        quando = adesso.strftime("%d/%m/%Y %H:%M")
        telegram.invia(telegram.componi(rilevanti, avvisi_nuovi, sito, quando))
    log.info("Fine: %s", controllo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
