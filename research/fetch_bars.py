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

# A liquid, optionable, multi-sector universe. This is a SURVIVORSHIP-BIASED
# sample: every name is one that still trades today. Companies that were liquid
# in 2014 and later blew up or were acquired are absent, which flatters any
# long-only trend strategy. The report states this; do not quietly forget it.
UNIVERSE = [
    # mega-cap tech
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "ORCL", "CRM", "ADBE",
    # semis / hardware
    "AMD", "MU", "INTC", "QCOM", "TXN", "DELL", "HPQ",
    # financials
    "JPM", "BAC", "WFC", "GS", "MS", "AXP", "SCHW", "MET", "PNC",
    # health
    "UNH", "JNJ", "PFE", "ABBV", "LLY", "TMO", "CVS",
    # consumer / retail
    "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD", "BBY",
    # industrials / energy / materials
    "CAT", "DE", "HON", "GE", "RTX", "LMT", "UNP", "PCAR", "MMM",
    "XOM", "CVX", "COP", "SLB", "BKR", "NEM", "FCX", "IP",
    # autos / telecom / staples
    "F", "GM", "T", "VZ", "KO", "PEP", "PG", "KHC", "ADM", "SYY",
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
