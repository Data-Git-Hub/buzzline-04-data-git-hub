"""
project_consumer_data-git-hub.py

Live FX visualization using Twelve Data WebSocket (intraday) with graceful fallback
to exchangerate.host for any symbols the WS server rejects for your plan.

- Multi-line chart of % change since session start (per symbol)
- WS heartbeat
- subscribe-status introspection (success/fail)
- Fallback polling only for WS-failed symbols

Docs notes:
- Connect: wss://ws.twelvedata.com/v1/quotes/price?apikey=YOUR_KEY
- Subscribe: {"action":"subscribe","params":{"symbols":"EUR/USD,USD/JPY,..."}}
- Trial/basic WS is limited; Pro is full WS access; trial allows up to 1 connection
  and ≤ 8 allowed symbols from their “trial list”. 1 WS credit per symbol on /quotes/price.
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

# Start with three; you can raise to ≤ 8 later or more depending on plan
SYMBOLS: List[str] = ["EUR/USD", "USD/JPY", "GBP/USD"]

# Rolling window size per symbol
MAX_TICKS_PER_SYMBOL = 300

# Animation cadence and fallback poll frequency
ANIMATE_INTERVAL_MS = 1000
FALLBACK_POLL_SECONDS = 60  # only for WS-failed symbols

# Twelve Data WS endpoint (key appended at runtime)
DEFAULT_TWELVE_WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"

# Fallback (keyless)
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

# Track which symbols have live WS ticks
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

                # Pull successes/fails into sets we can use later
                succ = {d.get("symbol") for d in obj.get("success", []) if d.get("symbol")}
                fail = {d.get("symbol") for d in obj.get("fails", []) if d.get("symbol")}
                # Update globals
                WS_ACTIVE.update(succ)
                WS_FAILED.update(fail)

                st = obj.get("status", "unknown")
                msg = obj.get("message") or obj.get("info") or obj.get("detail") or ""
                print(f"[WS] subscribe-status: {st} {msg}")
                if succ:
                    print(f"[WS] live ticks: {sorted(succ)}")
                if fail:
                    print(f"[WS] WS-rejected (fallback via exchangerate.host): {sorted(fail)}")
                continue

            parsed = parse_price_message(obj)
            if parsed is None:
                continue
            sym, price, ts_s = parsed
            if sym in store:
                store[sym].append((ts_s, price))
                WS_ACTIVE.add(sym)  # defensive (in case status missed)
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
# Fallback polling (only for WS-failed symbols)
# -----------------------

def poll_exchangerate_host_once(symbols: List[str]) -> None:
    base_url = os.getenv("EXHOST_BASE", EXHOST_BASE)
    # derive distinct non-USD legs to request with base=USD
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
                price = float(rates[quote])        # USD->quote
            elif quote == "USD" and base in rates and float(rates[base]) != 0.0:
                price = 1.0 / float(rates[base])   # base->USD inverted
            else:
                continue
            store[pair].append((now, price))
    except Exception:
        traceback.print_exc()

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
    ax.set_title("Live FX: % Change Since Session Start (UTC)")
    ax.set_xlabel("Time")
    ax.set_ylabel("% change")
    ax.grid(True, axis="both")
    return []

def update_chart(_frame_idx):
    # If some symbols were rejected, poll fallback ONLY for those
    rejected = sorted(s for s in SYMBOLS if (s in WS_FAILED))
    if rejected:
        # rate-limit polls
        if (update_chart._last_poll is None) or (time.time() - update_chart._last_poll >= FALLBACK_POLL_SECONDS):
            poll_exchangerate_host_once(rejected)
            update_chart._last_poll = time.time()

    # If NONE have data yet (cold start), poll once for all to seed lines
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
        print("[WS] No TWELVE_DATA_API_KEY found (.env or secrets/). Fallback only.")
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
