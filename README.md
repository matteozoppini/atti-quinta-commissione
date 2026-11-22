# Atti della Giunta regionale toscana per la V Commissione

Il sistema controlla automaticamente **tre volte al giorno** la banca dati degli atti della Regione Toscana: delibere, decisioni e proposte della Giunta, decreti del Presidente e decreti dirigenziali.

- Seleziona gli atti di competenza della V Commissione (istruzione, formazione, beni e attività culturali).
- Li pubblica su una pagina web consultabile.
- Manda un riepilogo su **Telegram solo quando ci sono novità**.

## Come vengono selezionati gli atti

Il perimetro è **strutturale**: non si basa su parole chiave. Il sistema guarda chi firma l'atto e da quale struttura proviene, leggendoli dal frontespizio del PDF ufficiale. Poi li confronta con l'organigramma della Giunta, che viene riletto a ogni controllo.

| Tipo di atto | Come si raccoglie | Come si decide |
|---|---|---|
| Decreti dirigenziali | Scansione completa, un giorno alla volta, più una ricerca per ciascun dirigente del perimetro (due controlli indipendenti) | Conta il **settore** indicato nel frontespizio |
| Atti di Giunta | Vengono letti tutti | Entrano se il **dirigente responsabile** guida un settore del perimetro, se la **direzione proponente** o una **struttura interessata** è del perimetro, oppure se propone un **assessore** con deleghe nelle materie della Commissione (in questo caso vanno "da verificare") |
| Decreti del Presidente | Vengono letti tutti | Conta la **struttura proponente**; le strutture trasversali vanno "da verificare" |

**Regola di prudenza:** se un atto è dubbio, ha competenze miste o il suo PDF non si legge, finisce in **"da verificare"** e non viene mai scartato. Anche gli atti esclusi restano consultabili sulla pagina, insieme al motivo dell'esclusione.

Il perimetro (settori, direzioni, assessori) si trova nel file **`perimetro.json`** e si modifica direttamente lì. Se l'organigramma cambia (nuovo dirigente, settore nuovo o soppresso), compare un avviso sulla pagina e su Telegram. I settori nuovi delle direzioni Istruzione e Beni vengono inclusi in automatico come "da verificare".

## Messa in funzione

### 1. Il repository e la pagina web
1. Crea il repository pubblico `atti-quinta-commissione` e caricaci questi file.
2. Vai in **Settings → Pages**. Alla voce *Build and deployment* scegli: Source **Deploy from a branch**, branch **main**, cartella **/docs**.
3. La pagina sarà su `https://matteozoppini.github.io/atti-quinta-commissione/`.
4. Vai in **Settings → Actions → General** e, alla voce *Workflow permissions*, scegli **Read and write permissions**.

### 2. Il bot Telegram (circa 2 minuti)
1. Su Telegram apri **@BotFather** e scrivi `/newbot`. Scegli un nome, per esempio *Atti V Commissione*, e un username che finisca in `bot`.
2. BotFather ti risponde con un **token**, una stringa del tipo `123456:ABC…`. Copialo.
3. Nel repository vai in **Settings → Secrets and variables → Actions → New repository secret** e crea il segreto `TELEGRAM_BOT_TOKEN` incollando il token.
4. Apri il tuo nuovo bot su Telegram e premi **Avvia** (`/start`).
5. In **Actions → "Strumenti (Telegram e prova PDF)" → Run workflow**, con azione `telegram-test`, nel registro (log) trovi la riga `TELEGRAM_CHAT_ID = …`.
6. Crea il segreto `TELEGRAM_CHAT_ID` con quel numero. Rilancia `telegram-test`: deve arrivarti il messaggio "Collegamento riuscito".

### 3. Riassunti scritti da Claude (facoltativo)
Se crei il segreto `ANTHROPIC_API_KEY`, i riassunti vengono scritti dal modello `claude-haiku-5-5`. Il costo è di pochi centesimi al mese.
Senza questa chiave il sistema usa una sintesi automatica: l'oggetto dell'atto più il primo punto del dispositivo.

### 4. Primo collaudo e archivio iniziale
1. In **Actions → Strumenti → Run workflow**, con azione `prova-pdf`, il sistema stampa i campi che legge da cinque atti reali. Serve a verificare che la lettura del frontespizio sia corretta.
2. In **Actions → Controllo atti → Run workflow**, inserisci `dal = 2025-11-10` (inizio della XII legislatura) e togli la spunta alla notifica. In questo modo si costruisce l'archivio. Il lavoro può richiedere più giri: i controlli successivi lo completano da soli.
3. Da quel momento i controlli partono da soli alle 7:40, 13:40 e 19:40 (ora italiana; un'ora più tardi con l'ora legale).

## Pagina di consultazione
- Gli atti sono in ordine cronologico, raggruppati per giorno, e si filtrano per stato (pertinenti / da verificare / esclusi), tipo di atto, tema, struttura, assessore e periodo. C'è anche una ricerca libera.
- Ogni scheda mostra la **sintesi**, la **parte dispositiva** evidenziata, il **motivo dell'inclusione**, i dati del frontespizio, gli allegati e i link al PDF e alla scheda ufficiale.
- Con la ★ segni gli atti di interesse. Le stelle restano salvate nel browser e si possono esportare e importare.
- Puoi selezionare più atti e scaricarli come **fascicolo PDF unico** con indice iniziale, allegati inclusi se vuoi.
- Il link `…/#atto=CODICE` apre direttamente la scheda di un atto: è il link che arriva nei messaggi Telegram.

## Struttura del codice
```
perimetro.json            settori, direzioni e assessori del perimetro
monitor/bancadati.py      interrogazione della banca dati atti (limite di 200 risultati gestito)
monitor/organigramma.py   organigramma e rilevazione dei cambiamenti
monitor/testo.py          lettura del frontespizio e della parte dispositiva dai PDF
monitor/classifica.py     regole del perimetro, ciascuna con il suo motivo
monitor/run.py            giro di controllo
docs/                     pagina web; in docs/data l'archivio JSON aggiornato a ogni controllo
```
Per lanciare i test in locale: `pip install -r requirements.txt pytest reportlab && python -m pytest -q`
