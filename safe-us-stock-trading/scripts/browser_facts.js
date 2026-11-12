// safe-us-stock-trading v5.3: one browser call for the SEC numbers the halal screen needs.
// Run in the built-in browser on a data.sec.gov tab (open https://data.sec.gov/submissions/CIK0000320193.json
// first), with T set to the stocks to screen. It reads SEC's own XBRL "company facts" and the filing list.
// It only REPORTS what the company filed: every value is from the newest balance-sheet date (instants) or the
// longest period ending on it (flows), in millions of USD. A tag that was not filed for that date is left
// out: missing means missing, never an older number. If "lag" is set, a newer 10-Q/10-K exists than the
// facts cover: read that filing itself. "israel" lists mentions in the newest filing (for the boycott
// screen's SEC source). Method borrowed from the open-source trader-skill pack (trader-analyst/facts.py).
const T = ["AAPL"];
const COMPACT = false;   // true: one short record a ticker for prescreen.py (values in the tag order below)
const INSTANT = ["Assets", "LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "CommercialPaper",
  "ShortTermBorrowings", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligations",
  "CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments", "ShortTermInvestments",
  "MarketableSecuritiesCurrent", "MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecurities",
  "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
  "LongTermInvestments", "AccountsReceivableNetCurrent"];
const FLOW = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenuesNetOfInterestExpense",
  "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "InvestmentIncomeInterest",
  "InvestmentIncomeInterestAndDividend", "InterestIncomeOther", "InterestAndOtherIncome", "InvestmentIncomeNet",
  "InterestIncomeOperating", "InterestExpense", "InterestExpenseNonoperating", "NonoperatingIncomeExpense"];
const FORMS = ["10-Q", "10-K", "20-F", "40-F"];
const m = v => Math.round(v / 1e5) / 10;
const map = await fetch("https://www.sec.gov/files/company_tickers.json").then(r => r.json()).catch(() => null);
const cikOf = t => { for (const k in map || {}) if (map[k].ticker === t) return String(map[k].cik_str).padStart(10, "0"); return null; };
const one = async t => {
  try {
    const cik = cikOf(t);
    if (!cik) return { error: map ? "ticker not in SEC's list" : "SEC ticker list not reachable" };
    const s = await fetch(`https://data.sec.gov/submissions/CIK${cik}.json`).then(r => r.json());
    const r = s.filings.recent; let f = null;
    for (let i = 0; i < r.form.length && !f; i++) if (FORMS.includes(r.form[i])) f = { form: r.form[i], filed: r.filingDate[i], period: r.reportDate[i],
      url: `https://www.sec.gov/Archives/edgar/data/${parseInt(cik, 10)}/${r.accessionNumber[i].replace(/-/g, "")}/${r.primaryDocument[i]}` };
    const facts = await fetch(`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`).then(r => r.json());
    const g = facts.facts["us-gaap"] || facts.facts["ifrs-full"] || {};
    const usd = k => ((g[k] && g[k].units && g[k].units.USD) || []).filter(x => FORMS.includes(x.form));
    const bs = usd("Assets").map(x => x.end).sort().pop();
    if (!bs) return { name: s.name, filing: f, error: "no balance sheet in SEC's facts: read the filing itself" };
    const instant = {}, flow = {};
    for (const k of INSTANT) { const x = usd(k).filter(x => x.end === bs && !x.start).pop(); if (x) instant[k] = m(x.val); }
    for (const k of FLOW) {
      const x = usd(k).filter(x => x.end === bs && x.start).sort((a, b) => (a.start < b.start ? -1 : 1))[0];
      if (x) flow[k] = [m(x.val), x.start];
    }
    const sh = ((facts.facts.dei || {}).EntityCommonStockSharesOutstanding || { units: {} }).units.shares || [];
    const so = sh.sort((a, b) => (a.end < b.end ? -1 : 1)).pop();
    let israel = null;
    if (f) try {
      const html = await fetch(f.url).then(r => (r.ok ? r.text() : ""));
      const x = new DOMParser().parseFromString(html, "text/html").body.innerText.replace(/\s+/g, " ");
      const hits = []; const re = /Israel/g; let h;
      while ((h = re.exec(x))) hits.push(x.slice(Math.max(0, h.index - 110), h.index + 130));
      israel = { count: hits.length, first: hits.slice(0, 3) };
    } catch (e) { israel = { error: "filing text not readable" }; }
    return { name: s.name, cik, filing: f, balance_sheet_date: bs, lag: f && f.period > bs ? `newest ${f.form} is for ${f.period}; facts stop at ${bs}` : null,
             shares_outstanding: so ? [so.val, so.end] : null, instant_musd: instant, flow_musd_from: flow, israel };
  } catch (e) { return { error: String(e).slice(0, 120) }; }
};
const full = Object.fromEntries(await Promise.all(T.map(async t => [t, await one(t)])));
const small = x => {
  if (x.error) return { e: x.error };
  const rev = FLOW.slice(0, 5).map(k => x.flow_musd_from[k]).find(Boolean), st = rev ? rev[1] : null;
  return { f: x.filing ? [x.filing.form, x.filing.filed, x.filing.period, x.filing.url.split("/").slice(-2).join("/")] : null,
           k: x.cik, bs: x.balance_sheet_date, lag: x.lag ? 1 : 0, so: x.shares_outstanding ? x.shares_outstanding[0] : null, st,
           i: INSTANT.map(k => (k in x.instant_musd ? x.instant_musd[k] : "")).join(","),
           fl: FLOW.map(k => (x.flow_musd_from[k] && x.flow_musd_from[k][1] === st ? x.flow_musd_from[k][0] : "")).join(","),
           il: x.israel ? (x.israel.error ? -1 : x.israel.count) : -1,
           is: x.israel && x.israel.first && x.israel.first[0] ? x.israel.first.map(h => h.slice(60, 200)).slice(0, 2) : undefined };
};
JSON.stringify({ read_at: new Date().toISOString(), source: "sec_edgar", compact: COMPACT ? 1 : 0,
                 tickers: COMPACT ? Object.fromEntries(Object.entries(full).map(([t, x]) => [t, small(x)])) : full });
