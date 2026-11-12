// safe-us-stock-trading v5.3: one browser call per boycott list, for every candidate at once.
// Open each site below in the built-in browser and run this same script on it (it looks at the address
// and does that site's check). Set NAMES (search words per ticker: the company, its parent and big
// subsidiaries; for a metal trust the sponsor, trustee and custodian) and FUNDS (ETF tickers).
//   1. https://investigate.afsc.org/company-search       AFSC Investigate (companies and fund look-through)
//   2. https://www.whoprofits.org/index.php/companies     Who Profits (reads every page of the list)
//   3. https://bdsmovement.net/get-involved/what-to-boycott   BDS targets
// OHCHR's list is a PDF annex: read the newest report once per session and check every name in one go.
// Each result has "ok": false when the site's own control check failed (the page changed or did not load):
// record that source as "unreachable", never as "no_match". A hit is a lead: open it and judge it.
const NAMES = { NVDA: ["nvidia", "mellanox"] };
const FUNDS = [];
const host = location.hostname.replace(/^www\./, "");
const doc = async u => new DOMParser().parseFromString(await fetch(u).then(r => r.text()), "text/html");
const txt = d => ((d.querySelector("main") || d.body).innerText || "").replace(/\s+/g, " ").trim();
const words = Object.entries(NAMES).flatMap(([t, ws]) => ws.map(w => [t, w.toLowerCase()]));
let out = { site: host, read_at: new Date().toISOString() };
if (host === "investigate.afsc.org") {
  const search = async w => {
    const d = await doc("/company-search?key=" + encodeURIComponent(w));
    return [...d.querySelectorAll('main a[href^="/company/"]')].map(a => a.getAttribute("href")).filter((x, i, a) => a.indexOf(x) === i);
  };
  out.ok = (await search("caterpillar")).length > 0;             // control: a company the database lists
  out.companies = {};
  for (const [t, w] of words) { const hits = await search(w); if (hits.length) (out.companies[t] = out.companies[t] || {})[w] = hits.map(h => "https://investigate.afsc.org" + h); }
  out.searched = words.map(x => x[1]);
  out.funds = {};
  for (const t of FUNDS) {
    const html = await fetch(`/fund-search?keyword=${encodeURIComponent(t)}&strict=0`).then(r => r.text());
    const m = html.match(/fund-url="([^"]+)"/);
    if (!m) { out.funds[t] = { found: false }; continue; }
    const s = txt(await doc(m[1])), i = s.indexOf("Companies on the BDS divestment shortlist"), j = s.indexOf("Download our Data");
    out.funds[t] = { found: true, url: "https://investigate.afsc.org" + m[1], summary: s.slice(i < 0 ? 0 : i, j < 0 ? 1600 : j).slice(0, 1600) };
  }
} else if (host === "whoprofits.org") {
  const names = new Set(); let pages = 0;
  for (let p = 1; p <= 80; p++) {
    const d = await doc("/index.php/companies?page=" + p), before = names.size;
    [...d.querySelectorAll('a[href*="/company/"]')].map(a => a.innerText.trim()).filter(Boolean).forEach(n => names.add(n));
    pages = p; if (names.size === before) break;
  }
  const all = [...names];
  out.ok = all.length > 300; out.pages = pages; out.listed = all.length; out.hits = {};
  for (const [t, w] of words) { const h = all.filter(n => n.toLowerCase().includes(w)); if (h.length) (out.hits[t] = out.hits[t] || []).push(...h); }
  out.searched = words.map(x => x[1]);
} else if (host === "bdsmovement.net") {
  const s = document.body.innerText.replace(/\s+/g, " ");
  out.ok = /Chevron|Carrefour|\bHP\b/.test(s) && s.length > 5000;   // control: long-standing named targets
  out.url = location.href; out.hits = {};
  for (const [t, w] of words) {
    const m = new RegExp("\\b" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "i").exec(s);
    if (m) (out.hits[t] = out.hits[t] || []).push(s.slice(Math.max(0, m.index - 100), m.index + 140));
  }
  out.searched = words.map(x => x[1]);
} else {
  out.ok = false; out.error = "run this on investigate.afsc.org, whoprofits.org or bdsmovement.net";
}
JSON.stringify(out);
