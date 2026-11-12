// safe-us-stock-trading v5.3: one browser call for every quote and a year of daily prices.
// Run in the built-in browser on a nasdaq.com tab (javascript tool). Set T and MODE first.
//   MODE "full": compact data for ingest.py (about 1.5 KB a ticker). Save the returned string as DATA.json,
//                exactly as returned, and run:  python3 ingest.py --data DATA.json ...
//                Every ticker carries a checksum, so a copying mistake is caught by ingest.py.
//   MODE "scan": a wide first look (10 to 30 tickers, about 60 characters each). Numbers are worked out in
//                the page and are for choosing a shortlist ONLY. Never report or size from them: fetch the
//                shortlist again in "full" mode.
const T = ["GLDM", "HLAL"];          // candidates + the market fund
const MODE = "full";                 // "full" or "scan"
const HL_ROWS = 25;                  // high/low are only needed for the newest rows (ATR 14, 20-day channel)
const day = d => { const [m, dd, y] = d.split("/"); return `${y}-${m}-${dd}`; };
const num = s => String(s).replace(/[$,]/g, "");
const cents = x => Math.round(parseFloat(x) * 100);
const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
const get = async t => {
  for (const cls of ["etf", "stocks"]) {
    try {
      const q = await fetch(`https://api.nasdaq.com/api/quote/${t}/info?assetclass=${cls}`).then(r => r.json());
      const p = q && q.data && q.data.primaryData;
      if (!p || !p.lastSalePrice) continue;
      const to = new Date().toISOString().slice(0, 10);
      const from = new Date(Date.now() - 390 * 864e5).toISOString().slice(0, 10);
      const h = await fetch(`https://api.nasdaq.com/api/quote/${t}/historical?assetclass=${cls}&fromdate=${from}&todate=${to}&limit=300`).then(r => r.json());
      const rows = (h.data.tradesTable.rows || []).reverse()
        .map(x => ({ d: day(x.date), c: cents(num(x.close)), h: cents(num(x.high)), l: cents(num(x.low)) }))
        .filter(r => r.c > 0 && r.h > 0 && r.l > 0);
      if (!rows.length) continue;
      return { cls, price: num(p.lastSalePrice), time: p.lastTradeTimestamp, realtime: !!p.isRealTime, rows };
    } catch (e) { /* try the next asset class */ }
  }
  return { error: "not found on Nasdaq" };
};
const got = await Promise.all(T.map(get));
let out;
if (MODE === "scan") {
  const pct = (a, b) => (b ? Math.round((a / b - 1) * 1000) / 10 : null);
  const lines = T.map((t, i) => {
    const g = got[i];
    if (g.error) return { t, line: `${t}|${g.error}`, key: -1e9 };
    const c = g.rows.map(r => r.c), n = c.length, px = cents(g.price);
    const a200 = n >= 200 ? pct(px, mean(c.slice(-200))) : null;
    const a50 = n >= 50 ? pct(px, mean(c.slice(-50))) : null;
    const mom = n >= 253 ? pct(c[n - 22], c[n - 253]) : null;
    let vol = null;
    if (n >= 127) {
      const r = []; for (let k = n - 126; k < n; k++) r.push(Math.log(c[k] / c[k - 1]));
      const m = mean(r); vol = Math.round(Math.sqrt(r.reduce((s, x) => s + (x - m) ** 2, 0) / (r.length - 1) * 252) * 1000) / 10;
    }
    const hint = a200 === null ? "?" : a200 < 0 && mom !== null && mom < 0 ? "AVOID" : a200 < 0 ? "CAUTION" : "OK";
    return { t, line: `${t}|${g.price}|${a200}|${a50}|${mom}|${vol}|${hint}`, key: (hint === "OK" ? 1000 : hint === "CAUTION" ? 0 : -1000) + (mom || 0) };
  }).sort((a, b) => b.key - a.key);
  out = { read_at: new Date().toISOString(), source: "nasdaq", mode: "scan",
          note: "pre-screen only: choose a shortlist, then fetch it in full mode. Never report these numbers.",
          cols: "ticker|price|% vs 200-day avg|% vs 50-day avg|12-1 month return %|126-day volatility %|trend",
          rows: lines.map(x => x.line) };
} else {
  const axes = [], tickers = {};
  T.forEach((t, i) => {
    const g = got[i];
    if (g.error) { tickers[t] = g; return; }
    const r = g.rows;
    let gaps = "", bad = false;
    for (let k = 1; k < r.length; k++) {
      const gap = Math.round((Date.parse(r[k].d) - Date.parse(r[k - 1].d)) / 864e5);
      if (gap < 1 || gap > 35) bad = true;
      gaps += gap.toString(36);
    }
    if (bad) { tickers[t] = { error: "price history has a gap over 35 days or is out of order" }; return; }
    const key = r[0].d + "|" + gaps;
    let ax = axes.findIndex(a => a.d0 + "|" + a.gaps === key);
    if (ax < 0) { axes.push({ d0: r[0].d, gaps }); ax = axes.length - 1; }
    const hl = r.slice(-HL_ROWS);
    const sum = (r.reduce((s, x) => s + x.c, 0) + hl.reduce((s, x) => s + x.h + x.l, 0)) % 1000000;
    tickers[t] = { cls: g.cls, price: g.price, time: g.time, realtime: g.realtime, ax, n: r.length, sum,
                   c: r.map(x => x.c.toString(36)).join(" "),
                   hl: hl.map(x => x.h.toString(36) + "." + x.l.toString(36)).join(" ") };
  });
  out = { v: 2, read_at: new Date().toISOString(), source: "nasdaq", axes, tickers };
}
JSON.stringify(out);
