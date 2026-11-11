// safe-us-stock-trading v5.0: one browser call for every quote and a year of daily prices.
// Run in the built-in browser on a nasdaq.com tab (javascript tool). Set T first, e.g.:
//   const T = ["GLDM", "HLAL"];          // candidates + the market fund
// The result is one JSON string. Save it as DATA.json and run:  python3 ingest.py --data DATA.json ...
const T = ["GLDM", "HLAL"];
const day = d => { const [m, dd, y] = d.split("/"); return `${y}-${m}-${dd}`; };
const num = s => String(s).replace(/[$,]/g, "");
const one = async t => {
  for (const cls of ["etf", "stocks"]) {
    try {
      const q = await fetch(`https://api.nasdaq.com/api/quote/${t}/info?assetclass=${cls}`).then(r => r.json());
      const p = q && q.data && q.data.primaryData;
      if (!p || !p.lastSalePrice) continue;
      const to = new Date().toISOString().slice(0, 10);
      const from = new Date(Date.now() - 420 * 864e5).toISOString().slice(0, 10);
      const h = await fetch(`https://api.nasdaq.com/api/quote/${t}/historical?assetclass=${cls}&fromdate=${from}&todate=${to}&limit=300`).then(r => r.json());
      const rows = (h.data.tradesTable.rows || []).reverse().map(x => [day(x.date), num(x.close), num(x.high), num(x.low)].join(","));
      return [t, { cls, price: num(p.lastSalePrice), time: p.lastTradeTimestamp, realtime: !!p.isRealTime, h: rows.join(";") }];
    } catch (e) { /* try the next asset class */ }
  }
  return [t, { error: "not found on Nasdaq" }];
};
JSON.stringify({ read_at: new Date().toISOString(), source: "nasdaq", tickers: Object.fromEntries(await Promise.all(T.map(one))) });
