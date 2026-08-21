"""Download daily OHLCV bars for the backtest universe.

Data source: Yahoo's public chart endpoint. Split-adjusted OHLCV, which matches
the `adjustment_type='split'` default the broker API documents as "the right
default for backtesting" — dividends are deliberately NOT adjusted in, because
the strategy trades price levels (prior highs, moving averages) and dividend
adjustment shifts those levels away from what a trader would actually have seen.

Writes one CSV per symbol to research/data/. Re-running skips symbols already
downloaded unless --force is passed.

    py research/fetch_bars.py            # fetch missing
    py research/fetch_bars.py --force    # re-fetch everything
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

# Benchmark first — the regime filter and relative-strength test both need it.
BENCHMARK = "SPY"

# SURVIVORSHIP BIAS — read before trusting any long-only result from this data.
#
# Every name below still trades today. Companies that were liquid and then
# failed or were acquired (SIVB, FRC, TWTR, ATVI, CERN, XLNX, …) are absent,
# which flatters any long-only strategy: the sample quietly excludes the worst
# outcomes. This was tested rather than assumed — the source returns ZERO bars
# for all six of those tickers, so the bias CANNOT be corrected here. Any
# future result must be read as an optimistic bound, and a negative result is
# therefore stronger than it looks.
#
# Breadth is the legitimate frequency lever: identical selectivity across ~7x
# the names yields ~7x the signals without touching a single entry gate.
UNIVERSE = [
    # --- mega/large-cap tech, software, internet ---
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "ORCL", "CRM",
    "ADBE", "NOW", "INTU", "IBM", "ACN", "CTSH", "EPAM", "IT", "ADSK", "ROP",
    "PTC", "TYL", "ANSS", "SNPS", "CDNS", "FTNT", "PANW", "CRWD", "ZS", "OKTA",
    "NET", "DDOG", "SNOW", "MDB", "TEAM", "WDAY", "VEEV", "HUBS", "ZM", "DOCU",
    "TWLO", "SHOP", "SQ", "PYPL", "FI", "GPN", "FIS", "MA", "V", "ADP",
    "PAYX", "CDW", "GDDY", "AKAM", "VRSN", "FFIV", "JNPR", "CSCO", "MSI", "ZBRA",
    # --- semis and hardware ---
    "AMD", "MU", "INTC", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "ADI", "NXPI",
    "MCHP", "ON", "SWKS", "QRVO", "MRVL", "TER", "ENTG", "SMCI", "ANET", "DELL",
    "HPQ", "HPE", "NTAP", "STX", "WDC", "PSTG", "KEYS", "TDY", "TRMB", "GRMN",
    "GLW", "APH", "TEL", "FLEX", "JBL", "SANM", "CLS", "LITE", "COHR", "MPWR",
    # --- financials: banks, brokers, cards ---
    "JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "AXP", "COF", "DFS",
    "SYF", "ALLY", "BK", "STT", "NTRS", "PNC", "USB", "TFC", "KEY", "RF",
    "CFG", "HBAN", "FITB", "MTB", "ZION", "CMA", "WAL", "PB", "SNV", "FHN",
    "BLK", "BX", "KKR", "APO", "ARES", "TROW", "BEN", "IVZ", "AMP", "RJF",
    "HOOD", "COIN", "SOFI", "LPLA", "MKTX", "CBOE", "CME", "ICE", "NDAQ", "SPGI",
    "MCO", "MSCI", "FDS", "TRU", "EFX", "FICO",
    # --- insurance ---
    "BRK-B", "PGR", "ALL", "TRV", "CB", "AIG", "MET", "PRU", "LNC", "PFG",
    "AFL", "UNM", "GL", "HIG", "CINF", "WRB", "AIZ", "ERIE", "RGA", "EG",
    # --- health care ---
    "UNH", "JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY", "AMGN", "GILD", "BIIB",
    "VRTX", "REGN", "MRNA", "ILMN", "TMO", "DHR", "ABT", "BDX", "BSX", "SYK",
    "ZBH", "EW", "ISRG", "MDT", "BAX", "HOLX", "RMD", "DXCM", "PODD", "ALGN",
    "XRAY", "CAH", "MCK", "COR", "CVS", "CI", "ELV", "HUM", "CNC", "MOH",
    "HCA", "UHS", "DVA", "IQV", "A", "WAT", "MTD", "PKI", "TECH", "CRL",
    "HIMS", "ZTS", "IDXX",
    # --- consumer discretionary / retail ---
    "WMT", "COST", "TGT", "HD", "LOW", "DG", "DLTR", "ROST", "TJX", "BURL",
    "BBY", "ORLY", "AZO", "AAP", "GPC", "LKQ", "TSCO", "ULTA", "LULU", "NKE",
    "DECK", "CROX", "SKX", "VFC", "PVH", "RL", "TPR", "KMX", "CVNA", "LAD",
    "AN", "PAG", "ABG", "GPI", "W", "CHWY", "ETSY", "EBAY", "BABA", "MELI",
    # --- restaurants / travel / leisure ---
    "MCD", "SBUX", "CMG", "YUM", "QSR", "DRI", "DPZ", "WEN", "TXRH", "EAT",
    "BKNG", "EXPE", "ABNB", "MAR", "HLT", "H", "WH", "CHH", "RCL", "CCL",
    "NCLH", "LVS", "WYNN", "MGM", "CZR", "DKNG", "LYV", "PLAY",
    # --- consumer staples ---
    "PG", "KO", "PEP", "KHC", "GIS", "K", "HSY", "SJM", "CPB", "CAG",
    "HRL", "TSN", "CL", "KMB", "CHD", "CLX", "EL", "COTY", "MO", "PM",
    "STZ", "TAP", "MNST", "KDP", "MDLZ", "SYY", "ADM", "BG", "KR", "ACI",
    # --- energy ---
    "XOM", "CVX", "COP", "EOG", "OXY", "HES", "DVN", "FANG", "MRO", "APA",
    "CTRA", "OVV", "SLB", "HAL", "BKR", "NOV", "FTI", "CHX", "WMB", "KMI",
    "OKE", "TRGP", "EPD", "ET", "MPLX", "PSX", "VLO", "MPC", "DINO", "PBF",
    # --- utilities ---
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "XEL", "ED", "WEC", "ES",
    "DTE", "AEE", "CMS", "CNP", "NI", "LNT", "EVRG", "PNW", "ATO", "SRE",
    "PEG", "PPL", "FE", "AES", "VST", "NRG", "CEG",
    # --- industrials ---
    "CAT", "DE", "HON", "GE", "MMM", "EMR", "ETN", "ITW", "PH", "ROK",
    "DOV", "IEX", "XYL", "FTV", "AME", "AOS", "SWK", "SNA", "PNR", "GGG",
    "RTX", "LMT", "NOC", "GD", "LHX", "HII", "TXT", "TDG", "HEI", "CW",
    "BA", "SPR", "UNP", "CSX", "NSC", "ODFL", "JBHT", "CHRW", "EXPD", "XPO",
    "SAIA", "LSTR", "UPS", "FDX", "DAL", "UAL", "AAL", "LUV", "ALK", "URI",
    "FAST", "GWW", "WSO", "POOL", "SITE", "BLD", "MAS", "FBIN", "OC", "WMS",
    "PCAR", "CMI", "PWR", "J", "ACM", "MTZ", "EME", "FIX",
    # --- materials ---
    "LIN", "APD", "SHW", "PPG", "RPM", "ECL", "NEM", "FCX", "AA", "CLF",
    "X", "NUE", "STLD", "CMC", "RS", "ATI", "CRS", "MP", "ALB", "CE",
    "EMN", "DOW", "LYB", "WLK", "OLN", "ASH", "IFF", "DD", "CTVA", "MOS",
    "CF", "NTR", "IP", "PKG", "SON", "SEE", "AMCR", "BALL", "CCK", "SLGN",
    # --- REITs ---
    "PLD", "AMT", "CCI", "EQIX", "DLR", "SPG", "O", "VICI", "WELL", "VTR",
    "ARE", "BXP", "KIM", "REG", "FRT", "ESS", "AVB", "EQR", "MAA", "UDR",
    "CPT", "INVH", "AMH", "EXR", "PSA", "CUBE", "IRM", "WY",
    # --- autos / transport equipment ---
    "F", "GM", "TSLA", "RIVN", "LCID", "STLA", "HMC", "TM", "RACE", "APTV",
    "BWA", "LEA", "ALV", "GT", "THRM",
    # --- telecom / media / entertainment ---
    "T", "VZ", "TMUS", "CMCSA", "CHTR", "DIS", "NFLX", "WBD", "PARA", "FOXA",
    "NWSA", "EA", "TTWO", "RBLX", "U", "MTCH", "PINS", "SNAP", "SPOT", "OMC",
    "IPG", "NYT",
]

CHART_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
             "?range={rng}&interval=1d")


def fetch(symbol: str, rng: str = "15y") -> list[dict]:
    """Return a list of bar dicts, oldest first. Raises on any problem —
    a silently short or empty series would corrupt the backtest."""
    req = urllib.request.Request(
        CHART_URL.format(sym=symbol, rng=rng),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)

    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"{symbol}: API error {chart['error']}")
    results = chart.get("result")
    if not results:
        raise RuntimeError(f"{symbol}: no result block")

    res = results[0]
    stamps = res.get("timestamp") or []
    quote = (res.get("indicators", {}).get("quote") or [{}])[0]

    rows: list[dict] = []
    for i, ts in enumerate(stamps):
        o, h, l, c = (quote.get("open") or [])[i], (quote.get("high") or [])[i], \
                     (quote.get("low") or [])[i], (quote.get("close") or [])[i]
        v = (quote.get("volume") or [])[i]
        # Yahoo emits nulls for halted/no-trade sessions. A bar missing any
        # field cannot be used for high/low/close logic, so drop it entirely
        # rather than forward-filling a price that never traded.
        if None in (o, h, l, c, v):
            continue
        rows.append({
            "date": time.strftime("%Y-%m-%d", time.gmtime(ts)),
            "open": f"{o:.6f}", "high": f"{h:.6f}",
            "low": f"{l:.6f}", "close": f"{c:.6f}", "volume": str(int(v)),
        })

    if len(rows) < 500:
        raise RuntimeError(f"{symbol}: only {len(rows)} bars — too short to backtest")
    return rows


def write_csv(symbol: str, rows: list[dict]) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{symbol}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(rows)
    return path


def main() -> int:
    force = "--force" in sys.argv
    symbols = [BENCHMARK] + UNIVERSE
    ok, skipped, failed = 0, 0, []

    for sym in symbols:
        path = os.path.join(DATA_DIR, f"{sym}.csv")
        if os.path.exists(path) and not force:
            skipped += 1
            continue
        try:
            rows = fetch(sym)
            write_csv(sym, rows)
            print(f"  {sym:<6} {len(rows):>5} bars  {rows[0]['date']} .. {rows[-1]['date']}")
            ok += 1
        except (urllib.error.URLError, RuntimeError, KeyError, IndexError, ValueError) as e:
            print(f"  {sym:<6} FAILED: {e}")
            failed.append(sym)
        time.sleep(0.6)   # be polite to a free endpoint

    print(f"\nfetched {ok}, skipped {skipped}, failed {len(failed)}")
    if failed:
        print(f"failed symbols: {', '.join(failed)}")
    # A partial universe is still usable, but the caller must know.
    return 0 if ok or skipped else 1


if __name__ == "__main__":
    sys.exit(main())
