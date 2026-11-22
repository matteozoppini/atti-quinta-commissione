"""Notifiche Telegram: un riepilogo per ogni controllo con novita' (nessun messaggio se non c'e' nulla)."""
from __future__ import annotations

import html
import logging
import os

import requests

log = logging.getLogger(__name__)
MAX = 3900

ETICHETTE_FONTE = {"G": "Atti della Giunta", "P": "Decreti del Presidente", "D": "Decreti dirigenziali"}
ICONA = {"pertinente": "🟢", "verifica": "🟠"}


def _data(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def componi(nuovi: list[dict], avvisi: list[str], sito: str, quando: str) -> list[str]:
    e = html.escape
    pert = sum(1 for a in nuovi if a["stato"] == "pertinente")
    ver = sum(1 for a in nuovi if a["stato"] == "verifica")
    righe = [f"<b>V Commissione · nuovi atti della Regione Toscana</b>",
             f"{e(quando)} · {len(nuovi)} nuovi: {pert} 🟢 pertinenti, {ver} 🟠 da verificare", ""]
    if len(nuovi) > 40:
        righe.append(f"Molti atti nuovi (aggiornamento dell'archivio): consultali sulla pagina.\n{sito}")
        nuovi = []
    for fonte in ("G", "P", "D"):
        gruppo = [a for a in nuovi if a["fonte"] == fonte]
        if not gruppo:
            continue
        righe.append(f"<b>{ETICHETTE_FONTE[fonte]}</b>")
        for a in sorted(gruppo, key=lambda x: (x["data"], x["numero"]), reverse=True):
            link = f"{sito}#atto={a['codice']}"
            righe.append(
                f"{ICONA.get(a['stato'], '')} <b>{e(a['tipo'])} n. {e(a['numero'])}</b> del {_data(a['data'])}\n"
                f"{e(a['oggetto'][:220])}\n"
                + (f"<i>{e(a['riassunto'][:300])}</i>\n" if a.get('riassunto_ia') else "")
                + f"<a href=\"{link}\">scheda</a> · <a href=\"{a['url_pdf']}\">PDF</a>"
                + ("" if a["stato"] == "pertinente" else f"\n↳ {e(a['motivi'][0][:160]) if a['motivi'] else ''}")
            )
            righe.append("")
    if avvisi:
        righe.append("<b>⚠️ Avvisi</b>")
        righe += [f"• {e(x)}" for x in avvisi]
    righe.append(f"\n<a href=\"{sito}\">Apri la pagina di consultazione</a>")

    messaggi, corrente = [], ""
    for r in righe:
        if len(corrente) + len(r) + 1 > MAX:
            messaggi.append(corrente)
            corrente = ""
        corrente += r + "\n"
    if corrente.strip():
        messaggi.append(corrente)
    return messaggi


def componi_riepilogo(atti: list[dict], dal: str, al: str, sito: str) -> list[str]:
    """Riepilogo compatto (una riga per atto) degli atti inclusi in un periodo."""
    e = html.escape
    pert = sum(1 for a in atti if a["stato"] == "pertinente")
    righe = [f"<b>V Commissione · riepilogo dal {_data(dal)} al {_data(al)}</b>",
             f"{len(atti)} atti: {pert} 🟢 pertinenti, {len(atti) - pert} 🟠 da verificare", ""]
    for fonte in ("G", "P", "D"):
        gruppo = sorted((a for a in atti if a["fonte"] == fonte), key=lambda x: (x["data"], x["numero"]), reverse=True)
        if not gruppo:
            continue
        righe.append(f"<b>{ETICHETTE_FONTE[fonte]} ({len(gruppo)})</b>")
        for a in gruppo:
            righe.append(f"{ICONA.get(a['stato'], '')} <a href=\"{sito}#atto={a['codice']}\">{e(a['tipo'])} {e(a['numero'])}</a> "
                         f"{_data(a['data'])[:5]} · {e(a['oggetto'][:110])}")
        righe.append("")
    righe.append(f"<a href=\"{sito}\">Apri la pagina di consultazione</a>")
    messaggi, corrente = [], ""
    for r in righe:
        if len(corrente) + len(r) + 1 > MAX:
            messaggi.append(corrente)
            corrente = ""
        corrente += r + "\n"
    if corrente.strip():
        messaggi.append(corrente)
    return messaggi


def invia(messaggi: list[str]) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID non impostati: notifica non inviata")
        return False
    ok = True
    for m in messaggi:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30, json={
            "chat_id": chat, "text": m, "parse_mode": "HTML", "disable_web_page_preview": True})
        if r.status_code != 200:
            log.error("Telegram: %s %s", r.status_code, r.text[:300])
            ok = False
    return ok


def trova_chat() -> None:
    """Stampa le chat che hanno scritto al bot (per ricavare TELEGRAM_CHAT_ID) e invia un messaggio di prova."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
    chats = {}
    for u in r.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        c = msg.get("chat")
        if c:
            chats[c["id"]] = c.get("username") or c.get("title") or c.get("first_name")
    if not chats:
        print("Nessun messaggio ricevuto dal bot: apri il bot su Telegram, premi Avvia (/start) e rilancia.")
    for cid, nome in chats.items():
        print(f"TELEGRAM_CHAT_ID = {cid}   ({nome})")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if chat:
        invia(["✅ Collegamento riuscito: qui arriveranno i riepiloghi degli atti della V Commissione."])
