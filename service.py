"""
The fly service: one real fruit fly brain, smelling fomo pages.

  POST /smell   a page in (theses + author PnLs, the taste numbers, the light from the
                meme, our own PnL if this is a revisit) -> a colour per card and one
                appetite out. Dopamine is applied, learning is saved.
  GET  /state   what the fly has learned, the calibration, the last page.

One process, one brain, a lock around every run. Rules that spend money (buy threshold,
size, stop) live in the page next to the wallet; this returns appetite only.
Design: ../fly_logic.md
"""
import json
import os
import threading
import time
from pathlib import Path

STATE = Path(os.environ.get("FLY_STATE_DIR", "state")); STATE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FLY_STATE_DIR", str(STATE))       # mushroom.py reads it at import

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from flysim import FlyBrain
from mushroom import MushroomBody
from nose import Nose
from tongue import Tongue

SCALE = float(os.environ.get("FLY_SCALE", "0.3"))
API_KEY = os.environ.get("FLY_API_KEY", "")
ADMIN_KEY = os.environ.get("FLY_ADMIN_KEY", "")     # the operator's key; never in the worker
ADMIN = STATE / "admin.json"                         # {"next_bid": usd | null, ...}
FILLS = STATE / "fills.jsonl"                        # every fill the page reports, one line each
SITE = STATE / "site.json"                           # what the page reads live: ca, url, mode, minUsd, maxUsd
FOMO = os.environ.get("FOMO_GATEWAY", "http://127.0.0.1:8791").rstrip("/")   # the fomo-api gateway (holds the fomo session and, in live mode, the wallet keys)
FOMO_KEY = os.environ.get("FOMO_API_KEY", "")
LIVE_SWITCH = os.environ.get("FLY_LIVE", "0") == "1"  # the hard switch on the box: without it no trade is ever sent, whatever the console says
DEDUPE_S = 600                                        # one buy and one sell per coin per ten minutes, however many viewers decide the same thing
SMELL_STEPS = 250          # 50 ms of brain time per thesis
THINK_STEPS = 500          # 100 ms think
KC_ELIGIBLE = 0.10         # the most active tenth of Kenyon cells may learn (APL-style sparseness)
LIGHT_GAIN = 0.08          # the meme's light pulse (-0.6..1.2) -> appetite
Z_DIV = 4.0                # appetite = z / Z_DIV + light * LIGHT_GAIN

app = FastAPI(title="fly")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
LOCK = threading.Lock()
WAITING = threading.Semaphore(3)     # more than three pages queued -> "busy", the page's toy decides that one
BOOT = time.time()
S = {"pages": 0, "theses": 0, "last": None, "errors": 0, "busy": 0, "cached": 0}
CACHE = {}                           # (address, thesis ids) -> (at, response): the same page within 90 s is one smell for everyone
CACHE_TTL = 90.0


def load_calib():
    p = STATE / "calib.json"
    if not p.exists():
        p = Path(__file__).parent / "state_calib.json"
    return json.loads(p.read_text())


CAL = load_calib()
print(f"fly: loading brain, scale {SCALE}, calib {CAL}")
fb = FlyBrain(str(Path(__file__).parent / "build" / "graph.npz"))
fb.wdata *= SCALE
mb = MushroomBody(fb, recover=0.01)   # forget() runs once per page: a floored synapse is back in ~100 pages
nose = Nose(fb, rate_hz=float(CAL["rate_hz"]), active=float(CAL["active"]))
tongue = Tongue(fb)
REC = {"ap": mb.reward_side, "av": mb.punish_side, "kc": mb.kc}
print(f"fly: {fb.n:,} neurons, mushroom body {mb.stats()}")


def merge(*drives):
    out = {}
    for d in drives:
        for k, v in d.items():
            out[k] = out.get(k, 0.0) + v
    return out


def score(out):
    ap, av = float(out["ap"].mean()), float(out["av"].mean())
    return (ap - av) / (ap + av + 2.0), ap, av


def z_of(s):
    return (s - CAL["median"]) / max(CAL["sd"], 1e-6)


def z_card(s):
    """A card is one thesis at full volume; it has its own naive baseline."""
    return (s - CAL.get("card_median", CAL["median"])) / max(CAL.get("card_sd", CAL["sd"]), 1e-6)


def admin_state():
    try:
        return json.loads(ADMIN.read_text()) if ADMIN.exists() else {"next_bid": None}
    except Exception:
        return {"next_bid": None}


def admin_write(d):
    ADMIN.write_text(json.dumps(d))


SITE_DEFAULT = {"ca": None, "url": None, "mode": "paper", "minUsd": 5.0, "maxUsd": 50.0}


def site_state():
    try:
        d = json.loads(SITE.read_text()) if SITE.exists() else {}
    except Exception:
        d = {}
    return {**SITE_DEFAULT, **d}


def site_write(**kw):
    d = site_state(); d.update(kw); d["at"] = int(time.time()); SITE.write_text(json.dumps(d)); return d


def fomo(method, path, body=None, timeout=60):
    """One call to the gateway."""
    import urllib.request, urllib.error
    req = urllib.request.Request(FOMO + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-api-key": FOMO_KEY, "content-type": "application/json"}, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"gateway {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        raise HTTPException(502, f"gateway unreachable: {str(e)[:120]}")


_acct = {"at": 0.0, "data": None}


_px = {"at": 0.0}


def _reprice(d):
    """Fresh prices on top of the snapshot: one /tokens/filter call for every open bag, at most every 4 s,
    however many viewers ask. fomo's own snapshot prices lag; this keeps unrealized PnL live."""
    now = time.time()
    pos = d.get("positions") or []
    if not pos or now - _px["at"] < 4.0:
        return d
    try:
        rows = fomo("POST", "/tokens/filter", [p["id"] for p in pos], timeout=15)
        px = {}
        for r in rows or []:
            t = (r or {}).get("token") or {}
            v = (r or {}).get("priceUSD")
            if t.get("address") and v:
                px[f"{t['address']}:{t['networkId']}"] = float(v)
        _px["at"] = now
    except Exception:
        return d
    total = 0.0; unreal = 0.0
    for p in pos:
        price = px.get(p["id"]) or p.get("price") or 0.0
        p["price"] = price; p["usd"] = (p.get("qty") or 0.0) * price
        cost = p.get("cost") or 0.0
        p["pnl"] = p["usd"] - cost if cost else 0.0
        p["pct"] = (p["pnl"] / cost * 100.0) if cost else 0.0
        total += p["usd"]; unreal += p["pnl"]
    d["positionsValue"] = total
    d["equity"] = (d.get("cash") or 0.0) + total
    pnl = d.get("pnl") or {}
    pnl["unrealized"] = unreal
    if pnl.get("realized") is not None:
        pnl["total"] = pnl["realized"] + unreal
    d["pnl"] = pnl
    d["pricedAt"] = now
    return d


def account(max_age=10.0):
    now = time.time()
    if _acct["data"] is not None and now - _acct["at"] < max_age:
        return _reprice(_acct["data"])
    d = fomo("GET", "/account")
    _acct.update(at=now, data=d)
    _px["at"] = 0.0
    return _reprice(d)


_cap = {"at": 0.0, "usd": None}


def gateway_cap():
    """The gateway's own per-trade ceiling (FOMO_MAX_TRADE_USD), read from /trade/wallet, cached 5 min."""
    now = time.time()
    if _cap["usd"] is not None and now - _cap["at"] < 300:
        return _cap["usd"]
    try:
        w = fomo("GET", "/trade/wallet", timeout=15)
        _cap.update(at=now, usd=float(w.get("maxTradeUsd") or 0) or None)
    except Exception:
        pass
    return _cap["usd"]


_recent = {}      # (tokenId, side) -> at


def live_trade(b):
    """A real fill through the gateway. Every rail in one place."""
    site = site_state()
    if site.get("mode") != "live":
        raise HTTPException(409, "paper mode")
    if not LIVE_SWITCH:
        raise HTTPException(409, "FLY_LIVE is not set on the box")
    side = str(b.get("side") or "").upper(); token = str(b.get("tokenId") or ""); sym = str(b.get("symbol") or "?")
    if side not in ("BUY", "SELL") or ":" not in token:
        raise HTTPException(400, "side and tokenId")
    key = (token, side); now = time.time()
    if now - _recent.get(key, 0) < DEDUPE_S:
        raise HTTPException(429, f"{side} {sym} already done in the last {DEDUPE_S // 60} min")
    if side == "BUY":
        usd = float(b.get("usd") or 0); pinned = bool(b.get("pinned"))
        a = admin_state()
        if pinned and a.get("next_bid"):
            usd = float(a["next_bid"])
        usd = max(float(site["minUsd"]), min(float(site["maxUsd"]), usd)) if not pinned else usd
        cap = gateway_cap()
        if cap and usd > cap:
            usd = cap                              # the gateway refuses anything above FOMO_MAX_TRADE_USD; never send a ticket it will 403
        if usd < 2:
            raise HTTPException(400, "fomo refuses swaps under $2")
        res = fomo("POST", "/trade/buy", {"tokenId": token, "usd": round(usd, 2)})
    else:
        pct = max(1.0, min(100.0, float(b.get("pct") or 100)))
        res = fomo("POST", "/trade/sell", {"tokenId": token, "pct": pct})
    _recent[key] = now
    _acct["at"] = 0.0                       # the next account read is fresh
    row = {"at": int(now), "side": side, "symbol": sym, "tokenId": token, "usd": b.get("usd"), "pct": b.get("pct"),
           "appetite": b.get("appetite"), "pinned": bool(b.get("pinned")), "live": True,
           "tx": res.get("txHash"), "status": res.get("status"), "confirmed": res.get("confirmed"), "swapUsd": res.get("swapUsdValue")}
    with FILLS.open("a") as f:
        f.write(json.dumps(row) + "\n")
    if side == "BUY" and b.get("pinned"):
        a = admin_state()
        if a.get("next_bid") is not None:
            admin_write({"next_bid": None, "spent": a.get("next_bid"), "spent_on": sym, "at": int(now)})
    print(f"LIVE {side} {sym} {token[:10]}… usd {row['usd']} pct {row['pct']} -> {res.get('status')} {str(res.get('txHash'))[:16]}", flush=True)
    return {"ok": True, **row, "result": res}


def eligible_kcs(out):
    """The most active tenth of Kenyon cells during this smell. Sparse, like a fly's."""
    r = out["kc"]
    if not len(r) or r.max() <= 0:
        return np.array([], dtype=np.int64)
    k = max(1, int(len(r) * KC_ELIGIBLE))
    top = np.argpartition(r, -k)[-k:]
    return mb.kc[top[r[top] > 0]]


def smell_page(body):
    t0 = time.time()
    theses = [t for t in (body.get("theses") or []) if t.get("id") and t.get("text")][:6]
    taste = body.get("taste") or {}
    light = float(body.get("light") or 0.0)
    own = body.get("ownPnl")
    sym = (body.get("token") or {}).get("symbol") or "?"
    vecs = nose.smells([{"id": t["id"], "text": t["text"]} for t in theses]) if theses else {}
    taste_drive = tongue.drive(taste)

    cards, seed = [], int(time.time() * 1000) % 100000
    for i, t in enumerate(theses):
        v = vecs[t["id"]]
        out = fb.run(merge(nose.drive(v), taste_drive), SMELL_STEPS, record=REC, seed=seed + i)
        s, ap, av = score(out)
        mb.observe(eligible_kcs(out))
        pnl = t.get("pnlPct")
        touched, kind, strength = 0, "none", 0.0
        if pnl is not None and abs(float(pnl)) > 1.0:
            kind = "reward" if float(pnl) > 0 else "punish"
            strength = min(1.0, abs(float(pnl)) / 50.0)
            touched = mb.dopamine(+1 if kind == "reward" else -1, strength)
        z = z_card(s)
        cards.append({"id": t["id"], "sweet": round(float(np.tanh(z / 2.0)), 3), "z": round(z, 2),
                      "intensity": round(nose.intensity(v), 3), "ap": round(ap, 1), "av": round(av, 1),
                      "dopamine": {"kind": kind, "strength": round(strength, 2), "synapses": int(touched)}})
    mb.apply()

    # our own money, on a revisit: the honest reward, twice as loud, paired with this page's smells
    own_touched = 0
    if own is not None and abs(float(own)) > 1.0:
        own_touched = mb.dopamine(+1 if float(own) > 0 else -1, min(1.0, abs(float(own)) / 50.0) * 2.0)
        mb.apply()

    # the think: the whole page at once, at half volume, plus the taste
    if theses:
        mix = np.mean([vecs[t["id"]] for t in theses], axis=0) * 0.5
        drive = merge(nose.drive(mix), taste_drive)
    else:
        drive = taste_drive
    out = fb.run(drive, THINK_STEPS, record=REC, seed=seed + 99)
    s, ap, av = score(out)
    z = z_of(s)
    appetite = float(np.clip(z / Z_DIV + light * LIGHT_GAIN, -1.0, 1.0))

    mb.forget(); mb.save()
    ms = int((time.time() - t0) * 1000)
    res = {"ok": True, "token": sym, "cards": cards, "appetite": round(appetite, 3), "z": round(z, 2),
           "ap": round(ap, 1), "av": round(av, 1), "fired": int(len(out["_fired"])), "light": light,
           "taste": tongue.word(taste), "ownDopamine": int(own_touched),
           "learning": mb.stats(), "ms": ms, "at": int(time.time()),
           "nextBid": admin_state().get("next_bid")}
    S["pages"] += 1; S["theses"] += len(theses); S["last"] = res
    print(f"smell ${sym}: {len(theses)} theses, taste {res['taste']}, light {light:+.2f} -> "
          f"appetite {appetite:+.3f} (z {z:+.2f}, ap {ap:.0f} av {av:.0f}) [{ms} ms]", flush=True)
    return res


def auth(x_api_key):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "bad key")


@app.post("/smell")
async def smell(req: Request, x_api_key: str | None = Header(default=None)):
    auth(x_api_key)
    body = await req.json()
    import asyncio
    loop = asyncio.get_running_loop()

    # one fly for everyone: the same page smelled by another visitor a moment ago is not smelled twice
    key = ((body.get("token") or {}).get("address"), tuple(sorted(t.get("id", "") for t in (body.get("theses") or [])[:6])))
    hit = CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL and body.get("ownPnl") is None:
        S["cached"] += 1
        return dict(hit[1], cached=True, nextBid=admin_state().get("next_bid"))

    def go():
        if not WAITING.acquire(blocking=False):
            S["busy"] += 1
            raise HTTPException(503, "busy")
        try:
            with LOCK:
                res = smell_page(body)
                CACHE[key] = (time.time(), res)
                if len(CACHE) > 200:
                    for k in sorted(CACHE, key=lambda k: CACHE[k][0])[:100]:
                        del CACHE[k]
                return res
        finally:
            WAITING.release()
    try:
        return await loop.run_in_executor(None, go)
    except HTTPException:
        raise
    except Exception as e:
        S["errors"] += 1
        print("smell failed:", repr(e)[:300], flush=True)
        raise HTTPException(500, str(e)[:200])


@app.get("/state")
def state(x_api_key: str | None = Header(default=None)):
    auth(x_api_key)
    return {"ok": True, "neurons": int(fb.n), "synapses": int(fb.W.nnz), "scale": SCALE, "calib": CAL,
            "rules": {"smellSteps": SMELL_STEPS, "thinkSteps": THINK_STEPS, "kcEligible": KC_ELIGIBLE,
                      "lightGain": LIGHT_GAIN, "zDiv": Z_DIV},
            "learning": mb.stats(), "pages": S["pages"], "theses": S["theses"], "errors": S["errors"], "busy": S["busy"], "cached": S["cached"],
            "last": S["last"], "uptime": int(time.time() - BOOT)}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/site")
def site(x_api_key: str | None = Header(default=None)):
    """What the page reads live: the contract address, paper or live, the ticket floor and cap."""
    auth(x_api_key)
    return {"ok": True, **site_state(), "liveSwitch": LIVE_SWITCH, "at": int(time.time())}


@app.get("/account")
async def acct(x_api_key: str | None = Header(default=None)):
    """The real account from the gateway: cash, equity, positions, fills with explorer links."""
    auth(x_api_key)
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, account)


@app.post("/trade")
async def trade(req: Request, x_api_key: str | None = Header(default=None)):
    auth(x_api_key)
    b = await req.json()
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: live_trade(b))


@app.post("/bought")
async def bought(req: Request, x_api_key: str | None = Header(default=None)):
    """The page reports a fill. A pinned next bid is spent by the buy that used it."""
    auth(x_api_key)
    b = await req.json()
    row = {"at": int(time.time()), "side": b.get("side"), "symbol": b.get("symbol"), "usd": b.get("usd"),
           "appetite": b.get("appetite"), "pinned": bool(b.get("pinned")), "equity": b.get("equity")}
    with FILLS.open("a") as f:
        f.write(json.dumps(row) + "\n")
    if b.get("side") == "BUY" and b.get("pinned"):
        a = admin_state()
        if a.get("next_bid") is not None:
            admin_write({"next_bid": None, "spent": a.get("next_bid"), "spent_on": b.get("symbol"), "at": int(time.time())})
            print(f"admin: pinned bid ${a.get('next_bid')} spent on ${b.get('symbol')}", flush=True)
    return {"ok": True, "nextBid": admin_state().get("next_bid")}


@app.post("/admin")
async def admin(req: Request, x_admin_key: str | None = Header(default=None)):
    """The operator's session. set_next_bid <usd> pins the next buy; reset lets the fly size its own."""
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(401, "bad admin key")
    b = await req.json(); cmd = str(b.get("cmd") or "")
    if cmd in ("set_next_bid", "set_bid"):
        usd = float(b.get("usd") or 0)
        if not (0 < usd < 1_000_000):
            raise HTTPException(400, "usd out of range")
        admin_write({"next_bid": usd, "at": int(time.time())})
        print(f"admin: next bid pinned at ${usd:.0f}", flush=True)
    elif cmd == "reset":
        admin_write({"next_bid": None, "at": int(time.time())})
        print("admin: next bid reset, the fly sizes its own", flush=True)
    elif cmd == "set_live":
        w = fomo("GET", "/trade/wallet")
        ok = bool(w.get("signerMatchesAccount")) and bool(w.get("tradingEnabled", True))
        if not ok:
            raise HTTPException(409, f"the gateway cannot sign: {json.dumps({k: w.get(k) for k in ('signerMatchesAccount', 'evmSignerMatchesAccount', 'tradingEnabled', 'maxTradeUsd')})}")
        if not LIVE_SWITCH:
            raise HTTPException(409, "FLY_LIVE=1 is not set in /opt/fly/.env on the box; set it and restart the service first")
        site_write(mode="live"); _acct["at"] = 0.0
        print("admin: LIVE. real money from here on.", flush=True)
    elif cmd == "trade_now":
        site_write(poke=int(time.time()))
        print("admin: trade now - the page trades the coin it is on", flush=True)
    elif cmd == "set_paper":
        site_write(mode="paper")
        print("admin: paper.", flush=True)
    elif cmd in ("set_min", "set_max"):
        usd = float(b.get("usd") or 0)
        if not (0 < usd < 1_000_000):
            raise HTTPException(400, "usd out of range")
        site_write(**({"minUsd": usd} if cmd == "set_min" else {"maxUsd": usd}))
        print(f"admin: {cmd} ${usd:.0f}", flush=True)
    elif cmd == "set_ca":
        ca = str(b.get("ca") or "").strip(); url = str(b.get("url") or "").strip() or None
        if not (20 <= len(ca) <= 64) or " " in ca:
            raise HTTPException(400, "that does not look like a contract address")
        site_write(ca=ca, url=url)   # keeps mode, floor and cap
        print(f"admin: CA set to {ca}" + (f" ({url})" if url else ""), flush=True)
    elif cmd in ("clear_ca", "remove_ca"):
        site_write(ca=None, url=None)
        print("admin: CA cleared", flush=True)
    elif cmd != "status":
        raise HTTPException(400, "unknown command")
    fills = []
    if FILLS.exists():
        fills = [json.loads(l) for l in FILLS.read_text().splitlines()[-10:] if l.strip()]
    last = S["last"] and {k: S["last"][k] for k in ("token", "appetite", "taste", "at")}
    return {"ok": True, "admin": admin_state(), "site": site_state(), "learning": mb.stats(), "pages": S["pages"], "last": last, "fills": fills}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("FLY_HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8792")))
