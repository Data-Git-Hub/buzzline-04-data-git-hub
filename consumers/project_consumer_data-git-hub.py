"""
project_consumer_data-git-hub.py

Live FX/Equity/Crypto visualization using Twelve Data WebSocket (intraday) with
graceful per-symbol fallback to Twelve Data REST /price (and, for EUR/USD only,
exchangerate.host if no API key is available).

Symbols:
  - EUR/USD  (forex)
  - AAPL     (US stock)
  - BTC/USD  (crypto)

Chart: Multi-line time series of % change since session start (per symbol).

Run (Windows PowerShell):
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
from typing import Dict, Deque, Tuple, List, Optional, Set
from datetime import datetime, timezone

# External deps
from dotenv import load_dotenv
import requests
from websocket import WebSocketApp

# Matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# -----------------------
# Configuration
# -----------------------

# Exactly the three you requested (note: Apple is "AAPL")
SYMBOLS: List[str] = ["EUR/USD", "AAPL", "BTC/USD"]

# Rolling window size per symbol
MAX_TICKS_PER_SYMBOL = 300

# Animation cadence and fallback poll frequency
ANIMATE_INTERVAL_MS = 1000
FALLBACK_POLL_SECONDS = 15  # modest interval for REST fallback

# Twelve Data WS endpoint (API key appended at runtime)
DEFAULT_TWELVE_WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"

# Twelve Data REST base (for /price fallback)
TD_REST_BASE = "https://api.twelvedata.com"

# Fiat-only keyless fallback (used only for EUR/USD if no API key)
EXHOST_BASE = "https://api.exchangerate.host"

# Heartbeat cadence
HEARTBEAT_SECONDS = 10

# -----------------------
# Secrets
# -----------------------

def load_api_key() -> Optional[str]:
    load_dotenv()
    key = os.getenv("TWELVE_DATA_API_KEY")
    if key:
        return key
    try:
        with open(os.path.join("secrets", "twelve_data.key"), "r", encoding="utf-8") as f:
            k2 = f.read().strip()
            return k2 or None
    except FileNotFoundError:
        return None

# -----------------------
# In-memory store
# -----------------------

Store = Dict[str, Deque[Tuple[float, float]]]
store: Store = {sym: deque(maxlen=MAX_TICKS_PER_SYMBOL) for sym in SYMBOLS}

# Track which symbols have live WS ticks (accepted) or were rejected
WS_ACTIVE: Set[str] = set()
WS_FAILED: Set[str] = set()

# Control
stop_event = threading.Event()
ws_thread: Optional[threading.Thread] = None

# -----------------------
# WS helpers
# -----------------------

def build_ws_url(api_key: Optional[str]) -> str:
    base = os.getenv("TWELVE_DATA_WS_URL", DEFAULT_TWELVE_WS_URL)
    return f"{base}?apikey={api_key}" if api_key else base

def build_subscribe_payload(symbols: List[str]) -> str:
    return json.dumps({"action": "subscribe", "params": {"symbols": ",".join(symbols)}})

def build_heartbeat_payload() -> str:
    return json.dumps({"action": "heartbeat"})

def parse_price_message(obj: dict) -> Optional[Tuple[str, float, float]]:
    # Accept 'price' / 'trade' / 'quote' generically
    ev = obj.get("event")
    if ev not in (None, "price", "trade", "quote"):
        return None
    sym = obj.get("symbol")
    if not sym:
        return None
    price = None
    for k in ("price", "last", "close", "bid"):
        if k in obj:
            try:
                price = float(obj[k])
                break
            except Exception:
                pass
    if price is None:
        return None
    ts = obj.get("timestamp")
    if isinstance(ts, (int, float)):
        ts_s = float(ts)
    elif isinstance(ts, str):
        try:
            ts_s = float(ts)
        except Exception:
            ts_s = time.time()
    else:
        ts_s = time.time()
    return (sym, price, ts_s)

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

                succ = {d.get("symbol") for d in obj.get("success", []) if d.get("symbol")}
                fail = {d.get("symbol") for d in obj.get("fails", []) if d.get("symbol")}
                WS_ACTIVE.update(succ)
                WS_FAILED.update(fail)

                st = obj.get("status", "unknown")
                msg = obj.get("message") or obj.get("info") or obj.get("detail") or ""
                print(f"[WS] subscribe-status: {st} {msg}")
                if succ:
                    print(f"[WS] live ticks: {sorted(succ)}")
                if fail:
                    print(f"[WS] WS-rejected (REST fallback): {sorted(fail)}")
                continue

            parsed = parse_price_message(obj)
            if parsed is None:
                continue
            sym, price, ts_s = parsed
            if sym in store:
                store[sym].append((ts_s, price))
                WS_ACTIVE.add(sym)  # defensive
    except Exception:
        traceback.print_exc()

def on_error(app: WebSocketApp, error):
    print(f"[WS] Error: {error}")

def on_close(app: WebSocketApp, status_code, msg):
    print(f"[WS] Closed: {status_code} {msg}")

def heartbeat_worker(app: WebSocketApp):
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
# Fallback polling
# -----------------------

def poll_twelvedata_price_once(symbols: List[str], api_key: Optional[str]) -> int:
    """
    Lightweight fallback using Twelve Data REST /price.
    Returns number of points added.
    """
    if not api_key or not symbols:
        return 0
    try:
        # Batch request: /price?symbol=AAPL,EUR/USD,BTC/USD&apikey=...
        url = f"{TD_REST_BASE}/price"
        params = {"symbol": ",".join(symbols), "apikey": api_key}
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        payload = resp.json()

        # Response can be a dict of dicts (one per symbol) or a single dict if one symbol
        now = time.time()
        added = 0

        if isinstance(payload, dict) and "price" in payload and "symbol" in payload:
            # Single
            sym = payload.get("symbol")
            price = float(payload.get("price"))
            if sym in store:
                store[sym].append((now, price))
                added += 1
        else:
            # Multi-symbol response: keys are symbols
            for sym, obj in payload.items():
                try:
                    price = float(obj.get("price"))
                except Exception:
                    continue
                if sym in store:
                    store[sym].append((now, price))
                    added += 1

        if added:
            print(f"[REST fallback] Added {added} point(s) for: {', '.join(symbols)}")
        return added

    except Exception:
        traceback.print_exc()
        return 0

def poll_exchangerate_host_eurusd_once() -> int:
    """
    Keyless fallback for EUR/USD only (if no Twelve Data API key).
    """
    try:
        resp = requests.get(
            f"{EXHOST_BASE}/latest",
            params={"base": "USD", "symbols": "EUR"},
            timeout=8,
        )
        resp.raise_for_status()
        j = resp.json()
        rate = float(j.get("rates", {}).get("EUR"))
        now = time.time()
        # USD->EUR = rate, so EUR/USD = 1 / rate
        price = 1.0 / rate if rate else None
        if price:
            store["EUR/USD"].append((now, price))
            print("[Fallback] Added 1 point for: EUR/USD (exchangerate.host)")
            return 1
    except Exception:
        traceback.print_exc()
    return 0

# -----------------------
# Timeseries builder (% change)
# -----------------------

def build_timeseries_pct(store: Store) -> Dict[str, Tuple[List[datetime], List[float]]]:
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
# Matplotlib: multi-line
# -----------------------

fig, ax = plt.subplots(figsize=(9, 5))

def init_chart():
    ax.clear()
    ax.set_title("Live Prices: % Change Since Session Start (UTC)")
    ax.set_xlabel("Time")
    ax.set_ylabel("% change")
    ax.grid(True, axis="both")
    return []

def update_chart(_frame_idx):
    # If some symbols were rejected by WS, poll TD REST for those
    rejected = sorted(s for s in SYMBOLS if (s in WS_FAILED))
    api_key = os.getenv("TWELVE_DATA_API_KEY")  # already loaded by load_dotenv()
    if rejected:
        if (update_chart._last_poll is None) or (time.time() - update_chart._last_poll >= FALLBACK_POLL_SECONDS):
            added = poll_twelvedata_price_once(rejected, api_key)
            # If no API key, at least try EUR/USD via exchangerate.host
            if added == 0 and api_key is None and "EUR/USD" in rejected:
                poll_exchangerate_host_eurusd_once()
            update_chart._last_poll = time.time()

    # If NONE have data yet (cold start), seed via REST for all three (cheap) to show lines ASAP
    if all(len(dq) == 0 for dq in store.values()):
        if (update_chart._last_poll is None) or (time.time() - update_chart._last_poll >= FALLBACK_POLL_SECONDS):
            poll_twelvedata_price_once(SYMBOLS, api_key)
            if api_key is None:
                poll_exchangerate_host_eurusd_once()
            update_chart._last_poll = time.time()

    series = build_timeseries_pct(store)

    ax.clear()
    ax.set_title("Live Prices: % Change Since Session Start (UTC)")
    ax.set_xlabel("Time")
    ax.set_ylabel("% change")
    ax.grid(True, axis="both")

    any_data = False
    for sym in SYMBOLS:
        times, pct = series.get(sym, ([], []))
        if times and pct:
            any_data = True
            ax.plot(times, pct, label=sym)

    if not any_data:
        ax.text(0.5, 0.5, "Waiting for data...", ha="center", va="center", transform=ax.transAxes)
        return []

    ax.legend(loc="best")
    return []

update_chart._last_poll = None  # type: ignore[attr-defined]

# -----------------------
# Main
# -----------------------

def main():
    api_key = load_api_key()
    if not api_key:
        print("[WS] No TWELVE_DATA_API_KEY found (.env or secrets/). WS may reject; REST fallback limited to EUR/USD for fiat only.")
    ws_url = build_ws_url(api_key)

    global ws_thread
    if api_key:
        print(f"[WS] Connecting: {ws_url}")
        ws_thread = threading.Thread(target=ws_worker, args=(ws_url, SYMBOLS), daemon=True)
        ws_thread.start()

    ani = FuncAnimation(
        fig,
        update_chart,
        init_func=init_chart,
        interval=ANIMATE_INTERVAL_MS,
        blit=False,
        cache_frame_data=False,  # silence cache warning
    )
    plt.tight_layout()
    plt.show()

    # Cleanup
    stop_event.set()
    if ws_thread and ws_thread.is_alive():
        ws_thread.join(timeout=3)

if __name__ == "__main__":
    main()
