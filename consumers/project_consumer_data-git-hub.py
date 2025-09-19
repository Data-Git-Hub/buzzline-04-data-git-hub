"""
project_consumer_data-git-hub.py

Live FX visualization:
1) Primary: Twelve Data WebSocket (intraday ticks)
2) Fallback: exchangerate.host polling (hourly/daily-level freshness)

Chart: Horizontal bar of % change since session start for a small basket of pairs.
"""

import os
import json
import time
import threading
import traceback
from collections import deque, defaultdict
from datetime import datetime, timezone
from typing import Dict, Deque, List, Tuple, Optional

# External libs
from dotenv import load_dotenv
import polars as pl
import requests
from websocket import WebSocketApp

# Matplotlib (no seaborn)
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# -----------------------
# Config
# -----------------------

# Choose ≤ 8 symbols to respect your Basic 8 WS credit
SYMBOLS: List[str] = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "USD/CHF", "AUD/USD"]

# Rolling window per symbol (ticks kept in memory)
MAX_TICKS_PER_SYMBOL = 300

# Animation / polling cadence
ANIMATE_INTERVAL_MS = 1000          # redraw every 1s
FALLBACK_POLL_SECONDS = 60          # when using exchangerate.host

# Twelve Data WebSocket defaults
DEFAULT_TWELVE_WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"  # confirm in TD docs
# NOTE: Twelve Data may use a subscription payload like:
# {"action":"subscribe","params":{"symbols":"EUR/USD,GBP/USD", "api_key":"YOUR_KEY"}}
# Please confirm the exact payload from your plan docs; adjust in build_subscribe_payload() below.

# exchangerate.host endpoint (keyless fallback)
EXHOST_BASE = "https://api.exchangerate.host"  # can override via env

# -----------------------
# Secrets loading
# -----------------------

def load_api_key() -> Optional[str]:
    load_dotenv()
    key = os.getenv("TWELVE_DATA_API_KEY")
    if key:
        return key

    # optional secrets/ fallback
    try:
        with open(os.path.join("secrets", "twelve_data.key"), "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    return None

# -----------------------
# Data store
# -----------------------

# Per-symbol rolling store of (timestamp, price)
Store = Dict[str, Deque[Tuple[float, float]]]
store: Store = {sym: deque(maxlen=MAX_TICKS_PER_SYMBOL) for sym in SYMBOLS}

# Thread control
ws_thread: Optional[threading.Thread] = None
stop_event = threading.Event()

# -----------------------
# Twelve Data WebSocket client
# -----------------------

def build_subscribe_payload(symbols: List[str], api_key: str) -> str:
    """
    Adjust this payload to match Twelve Data WS docs for your plan.
    Many WS APIs accept a JSON like:
      {"action":"subscribe","params":{"symbols":"EUR/USD,GBP/USD","api_key":"KEY"}}
    """
    return json.dumps({
        "action": "subscribe",
        "params": {
            "symbols": ",".join(symbols),
            "api_key": api_key
        }
    })

def on_message(app: WebSocketApp, message: str):
    try:
        data = json.loads(message)
        # Expected shape: include symbol and price/last fields; adjust per TD spec.
        # Common patterns:
        # data = {"symbol":"EUR/USD","price":"1.0895","timestamp": 1726660000}
        # Some feeds send "bid", "ask" or "last". We'll try a few keys.
        symbol = data.get("symbol")
        if not symbol:
            return

        # Extract a float price
        price = None
        for key in ("price", "last", "close", "bid"):
            v = data.get(key)
            if v is not None:
                try:
                    price = float(v)
                    break
                except Exception:
                    pass
        if price is None:
            return

        # Timestamp (seconds). If missing, use now.
        ts = data.get("timestamp")
        if ts is None:
            ts = time.time()
        elif isinstance(ts, (int, float)):
            ts = float(ts)
        else:
            # if string, try parse; else fallback to now
            try:
                ts = float(ts)
            except Exception:
                ts = time.time()

        if symbol in store:
            store[symbol].append((ts, price))
        # else: ignore symbols we didn't subscribe to
    except Exception:
        # Avoid crashing WS thread on malformed messages
        traceback.print_exc()

def on_error(app: WebSocketApp, error):
    print(f"[WS] Error: {error}")

def on_close(app: WebSocketApp, status_code, msg):
    print(f"[WS] Closed: {status_code} {msg}")

def on_open(app: WebSocketApp, api_key: str, symbols: List[str]):
    try:
        payload = build_subscribe_payload(symbols, api_key)
        app.send(payload)
        print(f"[WS] Subscribed to: {', '.join(symbols)}")
    except Exception:
        traceback.print_exc()

def ws_worker(ws_url: str, api_key: str, symbols: List[str]):
    """Run WS in a loop with basic reconnects."""
    while not stop_event.is_set():
        try:
            app = WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            # Bind on_open with args
            app.on_open = lambda a: on_open(a, api_key, symbols)
            app.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print(f"[WS] Worker exception, reconnecting in 5s: {e}")
        # backoff before reconnect
        if not stop_event.is_set():
            time.sleep(5)

# -----------------------
# Fallback: exchangerate.host polling
# -----------------------

def poll_exchangerate_host_once(symbols: List[str]) -> None:
    """
    Pull latest rates using USD as pivot, then map to requested pairs.
    For simplicity, when pair is X/USD or USD/X, derive from a USD base response.
    """
    base_url = os.getenv("EXHOST_BASE", EXHOST_BASE)
    # Get a USD base snapshot of a superset of currencies we need
    # Example: https://api.exchangerate.host/latest?base=USD&symbols=EUR,GBP,JPY,CAD,CHF,AUD
    target_ccys = sorted({p.split("/")[0] if p.startswith("USD/") else p.split("/")[1] for p in symbols})
    symbols_param = ",".join(target_ccys)
    url = f"{base_url}/latest"
    try:
        resp = requests.get(url, params={"base": "USD", "symbols": symbols_param}, timeout=10)
        resp.raise_for_status()
        j = resp.json()
        rates = j.get("rates", {})
        now = time.time()

        for pair in symbols:
            base, quote = pair.split("/")
            # If pair is USD/XXX, price is rate of quote (USD→quote)
            # If pair is XXX/USD, price is 1 / (USD→XXX)
            if base == "USD" and quote in rates:
                price = float(rates[quote])
            elif quote == "USD" and base in rates and rates[base] != 0:
                price = 1.0 / float(rates[base])
            else:
                continue
            store[pair].append((now, price))
    except Exception:
        traceback.print_exc()

# -----------------------
# Data → Polars → % change
# -----------------------

def build_dataframe_now(store: Store) -> pl.DataFrame:
    """
    Convert current rolling store to a tidy long DF: [symbol, ts, price]
    Then compute % change per symbol relative to that symbol's first observed price.
    """
    rows = []
    for sym, dq in store.items():
        for ts, px in dq:
            rows.append((sym, ts, px))
    if not rows:
        return pl.DataFrame({"symbol": [], "ts": [], "price": [], "pct_change": []})

    df = pl.DataFrame(rows, schema=["symbol", "ts", "price"])
    # Compute per-symbol first price and last price
    # first price per symbol
    firsts = (
        df.sort("ts")
          .group_by("symbol")
          .agg(pl.col("price").first().alias("p0"))
    )
    # latest price per symbol
    lasts = (
        df.sort("ts")
          .group_by("symbol")
          .agg(pl.col("price").last().alias("plast"))
    )
    joined = lasts.join(firsts, on="symbol", how="inner")
    out = joined.with_columns(
        ((pl.col("plast") / pl.col("p0")) - 1.0) * 100.0
        .alias("pct_change")
    ).select(["symbol", "pct_change"])

    return out

# -----------------------
# Matplotlib animation
# -----------------------

fig, ax = plt.subplots(figsize=(8, 5))
bar_containers = None

def init_chart():
    ax.clear()
    ax.set_title("Live FX: % Change Since Session Start")
    ax.set_xlabel("% change")
    ax.set_xlim(-2, 2)  # you can widen/narrow after you see typical ranges
    ax.grid(True, axis="x")
    return []

def update_chart(_frame_idx):
    # If WS hasn’t produced data yet, try fallback poll occasionally
    if all(len(dq) == 0 for dq in store.values()):
        poll_exchangerate_host_once(SYMBOLS)

    df = build_dataframe_now(store)
    ax.clear()
    ax.set_title("Live FX: % Change Since Session Start")
    ax.set_xlabel("% change")
    ax.grid(True, axis="x")

    if df.height == 0:
        ax.text(0.5, 0.5, "Waiting for data...", ha="center", va="center", transform=ax.transAxes)
        return []

    # Sort by pct_change
    df_sorted = df.sort("pct_change")
    symbols = df_sorted["symbol"].to_list()
    values = df_sorted["pct_change"].to_list()

    # horizontal bar
    y_pos = range(len(symbols))
    ax.barh(list(y_pos), values)
    ax.set_yticks(list(y_pos), labels=symbols)

    # Expand x-limits to fit data with some margin
    lo = min(values + [0.0])
    hi = max(values + [0.0])
    span = max(0.5, (hi - lo) * 1.2)
    center = (hi + lo) / 2
    ax.set_xlim(center - span/2, center + span/2)

    # Annotate bars
    for i, v in enumerate(values):
        ax.text(v, i, f" {v:.3f}%", va="center")

    return []

def main():
    api_key = load_api_key()
    ws_url = os.getenv("TWELVE_DATA_WS_URL", DEFAULT_TWELVE_WS_URL)

    # Start WS thread if we have a key
    if api_key:
        print("[WS] Starting Twelve Data WebSocket client...")
        global ws_thread
        ws_thread = threading.Thread(
            target=ws_worker, args=(ws_url, api_key, SYMBOLS), daemon=True
        )
        ws_thread.start()
    else:
        print("[WS] No API key found. Running fallback polling only.")

    # Start animation
    ani = FuncAnimation(fig, update_chart, init_func=init_chart, interval=ANIMATE_INTERVAL_MS, blit=False)
    plt.tight_layout()
    plt.show()

    # Cleanup
    stop_event.set()
    if ws_thread and ws_thread.is_alive():
        ws_thread.join(timeout=3)

if __name__ == "__main__":
    main()