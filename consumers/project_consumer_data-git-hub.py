"""
project_consumer_data-git-hub.py

Live FX visualization using Twelve Data WebSocket (intraday) with a fallback to
exchangerate.host polling.

Chart: Multi-line time series of % change since session start (per symbol).

Prereqs
-------
- requirements.txt should include: polars, websocket-client, requests, python-dotenv, matplotlib
- Create .env with: TWELVE_DATA_API_KEY=YOUR_KEY
- Ensure .env and secrets/ are git-ignored.

Run
---
PowerShell:
    .\.venv\Scripts\activate
    py -m consumers.project_consumer_data-git-hub
"""

from __future__ import annotations

import os
import json
import time
import threading
import traceback
from collections import deque
from typing import Dict, Deque, Tuple, List, Optional
from datetime import datetime, timezone

# External dependencies
from dotenv import load_dotenv
import polars as pl  # reserved for future aggregations; not strictly required for the line chart logic
import requests
from websocket import WebSocketApp

# Matplotlib (no seaborn, single figure)
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# -----------------------
# Configuration
# -----------------------

# (#4) Trimmed symbol basket for initial testing (raise up to ≤ 8 later)
SYMBOLS: List[str] = ["EUR/USD", "USD/JPY", "GBP/USD"]

# Rolling window of ticks per symbol (kept in memory)
MAX_TICKS_PER_SYMBOL = 300

# Animation cadence and fallback poll frequency
ANIMATE_INTERVAL_MS = 1000
FALLBACK_POLL_SECONDS = 60

# Twelve Data WebSocket default endpoint (append ?apikey= at runtime)
DEFAULT_TWELVE_WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"

# exchangerate.host (keyless fallback)
EXHOST_BASE = "https://api.exchangerate.host"

# Heartbeat every 10 seconds
HEARTBEAT_SECONDS = 10

# -----------------------
# Secrets loading
# -----------------------

def load_api_key() -> Optional[str]:
    """Load Twelve Data API key from .env or secrets/twelve_data.key."""
    load_dotenv()
    key = os.getenv("TWELVE_DATA_API_KEY")
    if key:
        return key
    try:
        with open(os.path.join("secrets", "twelve_data.key"), "r", encoding="utf-8") as f:
            key2 = f.read().strip()
            return key2 or None
    except FileNotFoundError:
        return None

# -----------------------
# In-memory rolling store
# -----------------------

# Store: per-symbol deque of (timestamp_seconds, price_float)
Store = Dict[str, Deque[Tuple[float, float]]]
store: Store = {sym: deque(maxlen=MAX_TICKS_PER_SYMBOL) for sym in SYMBOLS}

# Control flags/threads
stop_event = threading.Event()
ws_thread: Optional[threading.Thread] = None

# -----------------------
# Twelve Data WebSocket client
# -----------------------

def build_ws_url(api_key: Optional[str]) -> str:
    base_ws = os.getenv("TWELVE_DATA_WS_URL", DEFAULT_TWELVE_WS_URL)
    return f"{base_ws}?apikey={api_key}" if api_key else base_ws

def build_subscribe_payload(symbols: List[str]) -> str:
    """
    Subscribe payload, per Twelve Data docs for /v1/quotes/price:
      {"action":"subscribe","params":{"symbols":"EUR/USD,USD/JPY,..."}}
    """
    return json.dumps({"action": "subscribe", "params": {"symbols": ",".join(symbols)}})

def build_heartbeat_payload() -> str:
    return json.dumps({"action": "heartbeat"})

def parse_price_message(obj: dict) -> Optional[Tuple[str, float, float]]:
    """
    Extract (symbol, price, ts_seconds) from a WS 'price' event (or equivalent).
    Returns None if not a price tick message.
    """
    event = obj.get("event")
    if event not in (None, "price", "trade", "quote"):
        return None

    symbol = obj.get("symbol")
    if not symbol:
        return None

    price_val = None
    for k in ("price", "last", "close", "bid"):
        if k in obj:
            try:
                price_val = float(obj[k])
                break
            except Exception:
                pass
    if price_val is None:
        return None

    ts = obj.get("timestamp")
    if isinstance(ts, (int, float)):
        ts_seconds = float(ts)
    elif isinstance(ts, str):
        try:
            ts_seconds = float(ts)
        except Exception:
            ts_seconds = time.time()
    else:
        ts_seconds = time.time()

    return (symbol, price_val, ts_seconds)

# (#2) Expanded status printing so we see exactly why we're getting a warning
def on_message(app: WebSocketApp, message: str):
    try:
        data = json.loads(message)
        batch = data if isinstance(data, list) else [data]
        for obj in batch:
            if obj.get("event") == "subscribe-status":
                print("[WS] subscribe-status raw:")
                try:
                    print(json.dumps(obj, indent=2, sort_keys=True))
                except Exception:
                    print(obj)
                st = obj.get("status", "unknown")
                msg = obj.get("message") or obj.get("info") or obj.get("detail") or ""
                print(f"[WS] subscribe-status: {st} {msg}")
                continue

            parsed = parse_price_message(obj)
            if parsed is None:
                continue
            symbol, price, ts_secs = parsed
            if symbol in store:
                store[symbol].append((ts_secs, price))
    except Exception:
        traceback.print_exc()

def on_error(app: WebSocketApp, error):
    print(f"[WS] Error: {error}")

def on_close(app: WebSocketApp, status_code, msg):
    print(f"[WS] Closed: {status_code} {msg}")

def heartbeat_worker(app: WebSocketApp):
    """Send periodic heartbeats until stop_event is set or the app stops."""
    while not stop_event.is_set() and getattr(app, "keep_running", False):
        try:
            app.send(build_heartbeat_payload())
        except Exception:
            pass
        for _ in range(HEARTBEAT_SECONDS):
            if stop_event.is_set() or not getattr(app, "keep_running", False):
                break
            time.sleep(1)

def on_open(app: WebSocketApp, symbols: List[str]):
    try:
        app.send(build_subscribe_payload(symbols))
        print(f"[WS] Subscribed to: {', '.join(symbols)}")
        t = threading.Thread(target=heartbeat_worker, args=(app,), daemon=True)
        t.start()
    except Exception:
        traceback.print_exc()

def ws_worker(ws_url: str, symbols: List[str]):
    """Run the WS client with basic reconnect logic."""
    while not stop_event.is_set():
        try:
            app = WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            app.on_open = lambda a: on_open(a, symbols)
            app.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print(f"[WS] Worker exception: {e}")
        if not stop_event.is_set():
            time.sleep(5)

# -----------------------
# Fallback: exchangerate.host polling
# -----------------------

def poll_exchangerate_host_once(symbols: List[str]) -> None:
    """
    Pull latest rates using USD as pivot, then derive requested pairs.
    Example request: /latest?base=USD&symbols=EUR,GBP,JPY,...
    """
    base_url = os.getenv("EXHOST_BASE", EXHOST_BASE)
    target_ccys = sorted({p.split("/")[0] if p.startswith("USD/") else p.split("/")[1] for p in symbols})
    try:
        resp = requests.get(
            f"{base_url}/latest",
            params={"base": "USD", "symbols": ",".join(target_ccys)},
            timeout=10,
        )
        resp.raise_for_status()
        j = resp.json()
        rates = j.get("rates", {})
        now = time.time()

        for pair in symbols:
            base, quote = pair.split("/")
            if base == "USD" and quote in rates:
                price = float(rates[quote])  # USD->quote
            elif quote == "USD" and base in rates and float(rates[base]) != 0.0:
                price = 1.0 / float(rates[base])  # base->USD inverted
            else:
                continue
            store[pair].append((now, price))
    except Exception:
        traceback.print_exc()

# -----------------------
# Build % change timeseries (per symbol)
# -----------------------

def build_timeseries_pct(store: Store) -> Dict[str, Tuple[List[datetime], List[float]]]:
    """
    For each symbol, compute % change vs the first observed price in the current window.
    Returns dict[symbol] -> (list[datetime], list[%change]).
    """
    out: Dict[str, Tuple[List[datetime], List[float]]] = {}
    for sym, dq in store.items():
        if not dq:
            out[sym] = ([], [])
            continue
        rows = sorted(dq, key=lambda t: t[0])
        ts_list = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts, _ in rows]
        px_list = [px for _, px in rows]
        p0 = px_list[0]
        if p0 == 0:
            pct = [0.0 for _ in px_list]
        else:
            pct = [((p / p0) - 1.0) * 100.0 for p in px_list]
        out[sym] = (ts_list, pct)
    return out

# -----------------------
# Matplotlib multi-line animation
# -----------------------

fig, ax = plt.subplots(figsize=(9, 5))

def init_chart():
    ax.clear()
    ax.set_title("Live FX: % Change Since Session Start (UTC)")
    ax.set_xlabel("Time")
    ax.set_ylabel("% change")
    ax.grid(True, axis="both")
    return []

def update_chart(_frame_idx):
    # If WS hasn't produced data yet, softly poll fallback
    if all(len(dq) == 0 for dq in store.values()):
        if (update_chart._last_poll is None) or (time.time() - update_chart._last_poll >= FALLBACK_POLL_SECONDS):
            poll_exchangerate_host_once(SYMBOLS)
            update_chart._last_poll = time.time()

    series = build_timeseries_pct(store)

    ax.clear()
    ax.set_title("Live FX: % Change Since Session Start (UTC)")
    ax.set_xlabel("Time")
    ax.set_ylabel("% change")
    ax.grid(True, axis="both")

    any_data = False
    for sym in SYMBOLS:
        times, pct = series.get(sym, ([], []))
        if times and pct:
            any_data = True
            ax.plot(times, pct, label=sym)  # no explicit colors

    if not any_data:
        ax.text(0.5, 0.5, "Waiting for data...", ha="center", va="center", transform=ax.transAxes)
        return []

    ax.legend(loc="best")
    return []

# attribute for rate-limited fallback polling
update_chart._last_poll = None  # type: ignore[attr-defined]

# -----------------------
# Main
# -----------------------

def main():
    api_key = load_api_key()
    if not api_key:
        print("[WS] No TWELVE_DATA_API_KEY found (.env or secrets/). Will attempt fallback only.")
    ws_url = build_ws_url(api_key)

    # Start WS client if we have a key
    global ws_thread
    if api_key:
        print(f"[WS] Connecting: {ws_url}")
        ws_thread = threading.Thread(target=ws_worker, args=(ws_url, SYMBOLS), daemon=True)
        ws_thread.start()

    # (#3) Disable frame-data caching to avoid the warning about unbounded cache
    ani = FuncAnimation(
        fig,
        update_chart,
        init_func=init_chart,
        interval=ANIMATE_INTERVAL_MS,
        blit=False,
        cache_frame_data=False,  # <— fix #3
    )
    plt.tight_layout()
    plt.show()

    # Cleanup
    stop_event.set()
    if ws_thread and ws_thread.is_alive():
        ws_thread.join(timeout=3)

if __name__ == "__main__":
    main()
