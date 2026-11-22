/* Pagina di consultazione degli atti per la V Commissione. Nessuna dipendenza esterna tranne pdf-lib (locale). */
"use strict";

const ST = { atti: [], indice: {}, filtrati: [], mostrati: 0, sel: new Set(), stelle: new Set(), aperto: null };
const PASSO = 80;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dataIt = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "");
const GIORNI = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"];
const MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
const giornoEsteso = (iso) => { const d = new Date(iso + "T12:00:00"); return `${GIORNI[d.getDay()]} ${d.getDate()} ${MESI[d.getMonth()]} ${d.getFullYear()}`; };

const GRUPPI = [
  { id: "del", nome: "Delibere", f: (a) => a.fonte === "G" && /^Delibera/i.test(a.tipo) },
  { id: "dec", nome: "Decisioni", f: (a) => a.fonte === "G" && /^Decisione/i.test(a.tipo) },
  { id: "cr", nome: "Proposte al Consiglio", f: (a) => a.fonte === "G" && /^(Proposta|Documento preliminare)/i.test(a.tipo) },
  { id: "altro", nome: "Comunicazioni e altro", f: (a) => a.fonte === "G" && !/^(Delibera|Decisione|Proposta|Documento preliminare)/i.test(a.tipo) },
  { id: "pres", nome: "Decreti del Presidente", f: (a) => a.fonte === "P" },
  { id: "dir", nome: "Decreti dirigenziali", f: (a) => a.fonte === "D" },
];
const ETICHETTA_FONTE = { G: "Giunta", P: "Presidente", D: "Dirigente" };
const ETICHETTA_STATO = { pertinente: "pertinente", verifica: "da verificare", escluso: "escluso" };
const F = { stato: "inclusi", tipi: new Set(), testo: "", tema: "", struttura: "", assessore: "", dal: "", al: "", novita: false, interesse: false };

/* ---------------- dati ---------------- */
async function carica() {
  try {
    const r = await fetch("data/indice.json", { cache: "no-store" });
    if (!r.ok) throw new Error("indice non disponibile");
    ST.indice = await r.json();
  } catch (e) {
    $("#aggiornato").textContent = "Archivio non ancora creato";
    $("#elenco").innerHTML = `<div class="vuoto">L'archivio sarà disponibile dopo il primo controllo automatico.</div>`;
    return;
  }
  const anni = ST.indice.anni || [];
  const liste = await Promise.all(anni.map((a) => fetch(`data/atti-${a}.json`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : [])).catch(() => [])));
  ST.atti = liste.flat().sort((x, y) => (y.data + y.fonte + String(y.numero).padStart(8, "0")).localeCompare(x.data + x.fonte + String(x.numero).padStart(8, "0")));
  ST.novita = new Set(ST.indice.novita || []);
  try { ST.stelle = new Set(JSON.parse(localStorage.getItem("v-stelle") || "[]")); } catch { ST.stelle = new Set(); }
  intestazione();
  popolaFiltri();
  leggiHash();
  applica();
}

function salvaStelle() { try { localStorage.setItem("v-stelle", JSON.stringify([...ST.stelle])); } catch {} }

/* ---------------- intestazione e riepilogo ---------------- */
function intestazione() {
  const i = ST.indice, c = i.controllo || {};
  const q = i.aggiornato ? new Date(i.aggiornato) : null;
  $("#aggiornato").innerHTML = q ? `Ultimo controllo: <b>${q.toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" })}</b><br>${c.giunta ?? 0} atti di Giunta, ${c.presidente ?? 0} del Presidente e ${c.decreti_totali ?? 0} decreti scansionati (finestra ${dataIt(c.dal)}–${dataIt(c.al)})` : "";
  const conta = (s) => ST.atti.filter((a) => a.stato === s).length;
  const nov = ST.atti.filter((a) => ST.novita.has(a.codice)).length;
  const t = [
    ["nov", nov, `novità del ${i.novita_quando ? dataIt(i.novita_quando.slice(0, 10)) : "—"}`, () => impostaFiltro({ novita: true, stato: "inclusi" })],
    ["per", conta("pertinente"), "pertinenti in archivio", () => impostaFiltro({ stato: "pertinente", novita: false })],
    ["ver", conta("verifica"), "da verificare", () => impostaFiltro({ stato: "verifica", novita: false })],
    ["esc", conta("escluso"), "esclusi (consultabili)", () => impostaFiltro({ stato: "escluso", novita: false })],
    ["", ST.stelle.size, "★ di interesse", () => impostaFiltro({ interesse: true, stato: "tutti", novita: false })],
  ];
  const box = $("#riepilogo");
  box.innerHTML = "";
  t.forEach(([cl, n, e, fn]) => {
    const d = document.createElement("div");
    d.className = "tessera " + cl;
    d.innerHTML = `<div class="n">${n}</div><div class="e">${esc(e)}</div>`;
    d.onclick = fn;
    box.appendChild(d);
  });
  const av = i.avvisi || [];
  if (av.length) {
    const recenti = av.slice(0, 8);
    $("#avvisi").hidden = false;
    $("#avvisi").innerHTML = `<details ${av.some((x) => x.quando === i.aggiornato) && av.filter((x) => x.quando === i.aggiornato).length <= 4 ? "open" : ""}><summary>⚠️ Avvisi su organigramma e controlli (${av.length})</summary><ul>${recenti.map((x) => `<li><b>${esc(dataIt(x.quando.slice(0, 10)))}</b> — ${esc(x.testo)}</li>`).join("")}</ul></details>`;
  }
}

function popolaFiltri() {
  const tipi = $("#f-tipo");
  tipi.innerHTML = "";
  GRUPPI.forEach((g) => {
    const n = ST.atti.filter(g.f).length;
    const b = document.createElement("button");
    b.className = "chip";
    b.dataset.id = g.id;
    b.innerHTML = `${esc(g.nome)}<span class="c">${n}</span>`;
    b.onclick = () => { F.tipi.has(g.id) ? F.tipi.delete(g.id) : F.tipi.add(g.id); b.classList.toggle("on"); applica(); };
    tipi.appendChild(b);
  });
  const opzioni = (sel, valori) => { const s = $(sel); [...new Set(valori.filter(Boolean))].sort((a, b) => a.localeCompare(b, "it")).forEach((v) => s.insertAdjacentHTML("beforeend", `<option>${esc(v)}</option>`)); };
  opzioni("#f-tema", ST.atti.flatMap((a) => a.temi || []));
  opzioni("#f-struttura", ST.atti.map(struttura));
  opzioni("#f-assessore", ST.atti.flatMap((a) => (a.frontespizio?.proponenti || []).map(titolo)));
}

const titolo = (s) => s.toLowerCase().replace(/(^|\s|')\S/g, (c) => c.toUpperCase());
const struttura = (a) => a.settore || a.frontespizio?.struttura_proponente || a.ufficio || "";

/* ---------------- filtri ---------------- */
function impostaFiltro(o) {
  Object.assign(F, o);
  document.querySelectorAll("#f-stato button").forEach((b) => b.classList.toggle("on", b.dataset.v === F.stato));
  $("#f-novita").checked = F.novita;
  $("#f-interesse").checked = F.interesse;
  applica();
}

function corrisponde(a) {
  if (F.stato === "inclusi" && a.stato === "escluso") return false;
  if (!["inclusi", "tutti"].includes(F.stato) && a.stato !== F.stato) return false;
  if (F.tipi.size && !GRUPPI.some((g) => F.tipi.has(g.id) && g.f(a))) return false;
  if (F.tema && !(a.temi || []).includes(F.tema)) return false;
  if (F.struttura && struttura(a) !== F.struttura) return false;
  if (F.assessore && !(a.frontespizio?.proponenti || []).map(titolo).includes(F.assessore)) return false;
  if (F.dal && a.data < F.dal) return false;
  if (F.al && a.data > F.al) return false;
  if (F.novita && !ST.novita.has(a.codice)) return false;
  if (F.interesse && !ST.stelle.has(a.codice)) return false;
  if (F.testo) {
    const h = [a.atto, a.oggetto, a.numero, a.dispositivo, a.riassunto, struttura(a), a.ufficio, (a.motivi || []).join(" "), (a.frontespizio?.proponenti || []).join(" "), a.frontespizio?.dirigente_responsabile].join(" ").toLowerCase();
    if (!F.testo.toLowerCase().split(/\s+/).every((p) => h.includes(p))) return false;
  }
  return true;
}

function applica() {
  ST.filtrati = ST.atti.filter(corrisponde);
  ST.mostrati = 0;
  $("#elenco").innerHTML = "";
  const n = ST.filtrati.length;
  const per = ST.filtrati.filter((a) => a.stato === "pertinente").length, ver = ST.filtrati.filter((a) => a.stato === "verifica").length;
  $("#conteggio").textContent = n ? `${n} atti · ${per} pertinenti · ${ver} da verificare · ${n - per - ver} esclusi` : "";
  if (!n) $("#elenco").innerHTML = `<div class="vuoto">Nessun atto con questi filtri.</div>`;
  altri();
}

function altri() {
  const box = $("#elenco");
  const fine = Math.min(ST.filtrati.length, ST.mostrati + PASSO);
  let ultimoGiorno = ST.mostrati ? ST.filtrati[ST.mostrati - 1].data : null;
  const frag = document.createDocumentFragment();
  for (let i = ST.mostrati; i < fine; i++) {
    const a = ST.filtrati[i];
    if (a.data !== ultimoGiorno) {
      const h = document.createElement("div");
      h.className = "giorno";
      h.textContent = giornoEsteso(a.data);
      frag.appendChild(h);
      ultimoGiorno = a.data;
    }
    frag.appendChild(scheda(a));
  }
  box.appendChild(frag);
  ST.mostrati = fine;
  $("#altri").hidden = ST.mostrati >= ST.filtrati.length;
  $("#altri").textContent = `Mostra altri (${ST.filtrati.length - ST.mostrati})`;
}

/* ---------------- schede ---------------- */
function scheda(a) {
  const d = document.createElement("article");
  d.className = `atto ${a.stato}`;
  d.id = "a-" + a.codice;
  const prop = (a.frontespizio?.proponenti || []).map(titolo).join(", ");
  d.innerHTML = `
    <div class="testa">
      <input type="checkbox" aria-label="Seleziona per il fascicolo" ${ST.sel.has(a.codice) ? "checked" : ""}>
      <div>
        <div class="titolo">
          <span class="tipo ${a.fonte}">${esc(ETICHETTA_FONTE[a.fonte])}</span>
          <span class="estremi">${esc(a.tipo)} n. ${esc(a.numero)} del ${dataIt(a.data)}</span>
          <span class="badge ${a.stato}">${ETICHETTA_STATO[a.stato]}</span>
          ${ST.novita.has(a.codice) ? '<span class="badge nuovo">nuovo</span>' : ""}
        </div>
        <div class="oggetto">${esc(a.oggetto)}</div>
        <div class="meta">${esc(struttura(a))}${prop ? " · " + esc(prop) : ""}${(a.temi || []).length ? " · " + esc(a.temi.join(", ")) : ""}</div>
      </div>
      <div class="azioni"><button class="stella ${ST.stelle.has(a.codice) ? "on" : ""}" title="Di interesse">★</button></div>
    </div>`;
  const [cb] = d.getElementsByTagName("input");
  cb.onclick = (e) => { e.stopPropagation(); cb.checked ? ST.sel.add(a.codice) : ST.sel.delete(a.codice); barra(); };
  const stella = d.querySelector(".stella");
  stella.onclick = (e) => {
    e.stopPropagation();
    ST.stelle.has(a.codice) ? ST.stelle.delete(a.codice) : ST.stelle.add(a.codice);
    stella.classList.toggle("on");
    salvaStelle();
    intestazione();
  };
  d.querySelector(".testa").onclick = () => apriChiudi(d, a);
  return d;
}

function dispositivoHtml(t) {
  if (!t) return "<em>Parte dispositiva non individuata automaticamente: aprire il PDF.</em>";
  const [verbo, ...resto] = t.split("\n");
  return `<span class="verbo">${esc(verbo)}</span>${esc(resto.join("\n"))}`;
}

function apriChiudi(d, a, forza) {
  const c = d.querySelector(".corpo");
  if (c && !forza) { c.remove(); d.classList.remove("aperto"); history.replaceState(null, "", location.pathname); return; }
  if (c) return;
  d.classList.add("aperto");
  history.replaceState(null, "", "#atto=" + a.codice);
  const fr = a.frontespizio || {};
  const righe = [
    ["Proponenti", (fr.proponenti || []).map(titolo).join(", ")],
    ["Direzione", (fr.direzioni || []).join("; ") || a.ufficio],
    ["Settore", a.settore || fr.settore],
    ["Dirigente responsabile", fr.dirigente_responsabile || fr.responsabile_settore],
    ["Direttore", fr.direttore],
    ["Struttura proponente", fr.struttura_proponente],
    ["Strutture interessate", (fr.strutture_interessate || []).join("; ")],
    ["Pubblicazione", a.pubblicazione],
    ["Codice", a.codice],
  ].filter(([, v]) => v);
  const corpo = document.createElement("div");
  corpo.className = "corpo";
  corpo.innerHTML = `
    ${a.stato !== "escluso" ? `<div><h3>In breve</h3><div class="riassunto">${esc(a.riassunto || a.oggetto)} ${a.riassunto && !a.riassunto_ia ? '<span class="ia">(sintesi automatica)</span>' : ""}</div></div>
    <div><h3>Parte dispositiva</h3><div class="dispositivo">${dispositivoHtml(a.dispositivo)}</div></div>` : ""}
    <div><h3>Perché è ${a.stato === "escluso" ? "escluso" : a.stato === "verifica" ? "da verificare" : "pertinente"}</h3><ul class="motivi">${(a.motivi || []).map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>
    <div><h3>Dati dell'atto</h3><dl class="dati">${righe.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl></div>
    ${(a.allegati || []).length ? `<div><h3>Allegati</h3><div class="bottoni">${a.allegati.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.descrizione || "Allegato")}</a>`).join("")}</div></div>` : ""}
    <div class="bottoni">
      <a href="${esc(a.url_pdf)}" target="_blank" rel="noopener">📄 PDF dell'atto</a>
      <a href="${esc(a.url_scheda)}" target="_blank" rel="noopener">Scheda ufficiale</a>
      <button data-copia>🔗 Copia link</button>
    </div>`;
  corpo.querySelector("[data-copia]").onclick = () => navigator.clipboard?.writeText(location.href.split("#")[0] + "#atto=" + a.codice);
  d.appendChild(corpo);
}

function leggiHash() {
  const m = location.hash.match(/atto=([A-Z0-9]+)/i);
  if (!m) return;
  const a = ST.atti.find((x) => x.codice === m[1]);
  if (!a) return;
  F.stato = "tutti";
  document.querySelectorAll("#f-stato button").forEach((b) => b.classList.toggle("on", b.dataset.v === "tutti"));
  setTimeout(() => {
    const i = ST.filtrati.indexOf(a);
    while (ST.mostrati <= i) altri();
    const d = document.getElementById("a-" + a.codice);
    if (d) { apriChiudi(d, a, true); d.scrollIntoView({ block: "center" }); d.classList.add("lampeggia"); }
  }, 0);
}

/* ---------------- selezione e fascicolo ---------------- */
function barra() {
  $("#barra").hidden = ST.sel.size === 0;
  $("#n-sel").textContent = `${ST.sel.size} atti selezionati`;
}

const WINANSI = /[^\x20-\x7E\xA0-\xFF‘’“”–—…€]/g;
const pulito = (s) => String(s || "").replace(/\s+/g, " ").replace(WINANSI, "?");

function aCapo(testo, font, size, larg) {
  const parole = pulito(testo).split(" "), righe = [];
  let r = "";
  for (const p of parole) {
    const prova = r ? r + " " + p : p;
    if (font.widthOfTextAtSize(prova, size) > larg && r) { righe.push(r); r = p; } else r = prova;
  }
  if (r) righe.push(r);
  return righe;
}

async function fascicolo() {
  const { PDFDocument, StandardFonts, rgb } = PDFLib;
  const atti = ST.atti.filter((a) => ST.sel.has(a.codice));
  const conAllegati = $("#con-allegati").checked;
  const prog = $("#progresso");
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica), grassetto = await doc.embedFont(StandardFonts.HelveticaBold);
  // indice
  let pag = doc.addPage([595, 842]), y = 790;
  const scrivi = (t, f = font, s = 10, col = rgb(0.1, 0.1, 0.1)) => {
    for (const riga of aCapo(t, f, s, 500)) {
      if (y < 60) { pag = doc.addPage([595, 842]); y = 790; }
      pag.drawText(riga, { x: 48, y, size: s, font: f, color: col });
      y -= s + 4;
    }
  };
  scrivi("Fascicolo atti - V Commissione", grassetto, 16);
  scrivi(`Creato il ${new Date().toLocaleString("it-IT")} - ${atti.length} atti`, font, 9, rgb(0.4, 0.4, 0.4));
  y -= 10;
  atti.forEach((a, i) => {
    scrivi(`${i + 1}. ${a.tipo} n. ${a.numero} del ${dataIt(a.data)} (${ETICHETTA_STATO[a.stato]})`, grassetto, 10);
    scrivi(a.oggetto, font, 9.5);
    if (a.riassunto && a.stato !== "escluso") scrivi("In breve: " + a.riassunto, font, 8.5, rgb(0.35, 0.35, 0.35));
    y -= 6;
  });
  const errori = [];
  for (const [i, a] of atti.entries()) {
    const fonti = [{ url: a.url_pdf, nome: a.atto }].concat(conAllegati ? (a.allegati || []).map((x) => ({ url: x.url, nome: x.descrizione })) : []);
    for (const f of fonti) {
      prog.textContent = `Scarico ${i + 1}/${atti.length}: ${f.nome}…`;
      try {
        const buf = await (await fetch(f.url)).arrayBuffer();
        const src = await PDFDocument.load(buf, { ignoreEncryption: true });
        const pagine = await doc.copyPages(src, src.getPageIndices());
        pagine.forEach((p) => doc.addPage(p));
      } catch (e) {
        errori.push(`${a.atto} - ${f.nome}`);
      }
    }
  }
  if (errori.length) {
    pag = doc.addPage([595, 842]); y = 790;
    scrivi("Documenti non inclusi (scaricarli dal link ufficiale):", grassetto, 11);
    errori.forEach((e) => scrivi("- " + e));
  }
  const bytes = await doc.save();
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `fascicolo-V-commissione-${new Date().toISOString().slice(0, 10)}.pdf`;
  link.click();
  prog.textContent = errori.length ? `Fatto, ${errori.length} documenti non scaricati (elencati in fondo al fascicolo)` : "Fascicolo pronto";
}

/* ---------------- perimetro ---------------- */
function mostraPerimetro(e) {
  e.preventDefault();
  const p = ST.indice.perimetro || {};
  const settori = Object.entries(p.settori || {});
  $("#perimetro-testo").innerHTML = `
    <h2>Come vengono selezionati gli atti</h2>
    <p>Nessun filtro per parole chiave: ogni atto è attribuito in base a <b>chi lo firma e da quale struttura proviene</b>, letti dal frontespizio del PDF ufficiale e confrontati con l'organigramma aggiornato a ogni controllo.</p>
    <ul>
      <li><b>Decreti dirigenziali</b>: scansione completa giorno per giorno + ricerca per ciascun dirigente del perimetro; decide il settore indicato nel frontespizio.</li>
      <li><b>Atti di Giunta</b>: letti tutti; inclusi se il dirigente responsabile guida un settore del perimetro, se la direzione proponente o una struttura interessata è del perimetro. Se propone un assessore con deleghe nelle materie della Commissione, l'atto è comunque messo «da verificare».</li>
      <li><b>Decreti del Presidente</b>: letti tutti; decide la struttura proponente (le strutture trasversali vanno «da verificare»).</li>
      <li>Nel dubbio, o se il PDF non è leggibile, l'atto è sempre <b>da verificare</b>, mai scartato. Anche gli esclusi restano consultabili con il motivo.</li>
    </ul>
    <table><tr><th>Settore</th><th>Tema</th><th>Stato</th></tr>
    ${settori.map(([cod, s]) => `<tr><td>${esc(cod)}</td><td>${esc(s.tema)}</td><td>${esc(ETICHETTA_STATO[s.stato])}</td></tr>`).join("")}</table>
    <p>Assessori segnalati: ${esc((p.assessori_segnalati || []).map(titolo).join(", "))}.</p>`;
  $("#perimetro").showModal();
}

/* ---------------- eventi ---------------- */
document.querySelectorAll("#f-stato button").forEach((b) => (b.onclick = () => impostaFiltro({ stato: b.dataset.v })));
let attesa;
$("#f-testo").oninput = (e) => { clearTimeout(attesa); attesa = setTimeout(() => { F.testo = e.target.value.trim(); applica(); }, 200); };
[["#f-tema", "tema"], ["#f-struttura", "struttura"], ["#f-assessore", "assessore"], ["#f-dal", "dal"], ["#f-al", "al"]].forEach(([s, k]) => ($(s).onchange = (e) => { F[k] = e.target.value; applica(); }));
$("#f-novita").onchange = (e) => impostaFiltro({ novita: e.target.checked });
$("#f-interesse").onchange = (e) => impostaFiltro({ interesse: e.target.checked });
$("#f-azzera").onclick = () => {
  Object.assign(F, { stato: "inclusi", testo: "", tema: "", struttura: "", assessore: "", dal: "", al: "", novita: false, interesse: false });
  F.tipi.clear();
  document.querySelectorAll(".chip").forEach((c) => c.classList.remove("on"));
  ["#f-testo", "#f-tema", "#f-struttura", "#f-assessore", "#f-dal", "#f-al"].forEach((s) => ($(s).value = ""));
  impostaFiltro({});
};
$("#altri").onclick = altri;
$("#scarica").onclick = () => fascicolo().catch((e) => ($("#progresso").textContent = "Errore: " + e.message));
$("#deseleziona").onclick = () => { ST.sel.clear(); document.querySelectorAll(".testa input").forEach((c) => (c.checked = false)); barra(); };
$("#sel-interesse").onclick = () => { ST.stelle.forEach((c) => ST.sel.add(c)); document.querySelectorAll(".atto").forEach((d) => { const c = d.id.slice(2); d.querySelector(".testa input").checked = ST.sel.has(c); }); barra(); };
$("#mostra-perimetro").onclick = mostraPerimetro;
$("#esporta").onclick = () => { const l = document.createElement("a"); l.href = URL.createObjectURL(new Blob([JSON.stringify([...ST.stelle])], { type: "application/json" })); l.download = "atti-di-interesse.json"; l.click(); };
$("#importa").onclick = () => $("#file-importa").click();
$("#file-importa").onchange = async (e) => { const t = await e.target.files[0].text(); JSON.parse(t).forEach((c) => ST.stelle.add(c)); salvaStelle(); intestazione(); applica(); };
window.addEventListener("hashchange", leggiHash);
carica();
