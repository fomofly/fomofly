"""
Calibration: real theses from fomo, through the nose, into the real brain.

Picks the odor volume (rate_hz, active share) where different theses give different
appetites (between-thesis spread > within-thesis noise) while Kenyon cells stay sparse,
then prints the untrained appetite distribution so the buy threshold can be set.
Run on the box:  FOMO_API_KEY=... .venv/bin/python calibrate.py
"""
import json, os, sys, time, urllib.request
import numpy as np
from flysim import FlyBrain
from mushroom import MushroomBody
from nose import Nose, embed
from tongue import Tongue

SCALE = float(os.environ.get("FLY_SCALE", "0.3"))
GW = os.environ.get("FOMO_GATEWAY", "http://127.0.0.1:8791").rstrip("/")
KEY = os.environ.get("FOMO_API_KEY", "")

def gw(path):
    req = urllib.request.Request(GW + path, headers={"x-api-key": KEY})
    return json.load(urllib.request.urlopen(req, timeout=30))

def real_theses(n_tokens=8):
    lb = gw("/leaderboard/24h")["leaderboard"][:25]
    agg = {}
    for u in lb:
        for h in u.get("topHoldings") or []:
            k = f'{h["tokenAddress"]}:{h["networkId"]}'
            a = agg.setdefault(k, {"address": h["tokenAddress"], "networkId": h["networkId"], "n": 0})
            a["n"] += 1
    toks = sorted(agg.values(), key=lambda a: -a["n"])[:n_tokens]
    out = []
    for t in toks:
        try:
            d = gw(f'/feed/token/thesis?tokenAddress={t["address"]}&networkId={t["networkId"]}')
        except Exception as e:
            print("  thesis fetch failed", t["address"][:8], e); continue
        for i in d.get("items") or []:
            c = i.get("comment") or {}
            if i.get("type") == "thesis" and c.get("comment"):
                at = i.get("authorTrade") or {}
                out.append({"id": str(i["id"]), "text": " ".join(str(c["comment"]).split())[:500],
                            "pnlPct": float(at.get("percentageUnrealizedPnl") or 0) if at else None,
                            "token": t["address"][:8]})
    return out

state = os.environ.get("FLY_STATE_DIR", "state"); os.makedirs(state, exist_ok=True)
cache = os.path.join(state, "calib_theses.json")
if os.path.exists(cache) and "--fresh" not in sys.argv:
    theses = json.load(open(cache))
else:
    theses = real_theses(); json.dump(theses, open(cache, "w"), indent=1)
print(f"{len(theses)} real theses from {len(set(t['token'] for t in theses))} tokens")
for t in theses[:5]: print("   ", t["pnlPct"], t["text"][:90])

fb = FlyBrain("build/graph.npz"); fb.wdata *= SCALE
mb = MushroomBody(fb); tongue = Tongue(fb)
rec = {"ap": mb.reward_side, "av": mb.punish_side, "kc": mb.kc}
E = embed([t["text"] for t in theses]); print("embedded", E.shape)

def appetite(out):
    ap, av = float(out["ap"].mean()), float(out["av"].mean())
    return (ap - av) / (ap + av + 2.0), ap, av, float(out["kc"].mean()), len(out["_fired"])

sample = theses[:24]
best = None
for rate in (8.0, 15.0, 25.0):
    for active in (0.2, 0.35):
        nose = Nose(fb, rate_hz=rate, active=active)
        vecs = [nose.receptors(e) for e in E]
        t0 = time.time(); apps, kcs, fired = [], [], []
        for i, th in enumerate(sample):
            out = fb.run(nose.drive(vecs[i]), 300, record=rec, seed=1)
            a, ap, av, kc, nf = appetite(out); apps.append(a); kcs.append(kc); fired.append(nf)
        within = []
        for i in range(0, 24, 4):
            a2 = appetite(fb.run(nose.drive(vecs[i]), 300, record=rec, seed=2))[0]
            within.append(abs(a2 - apps[i]))
        between = float(np.std(apps)); noise = float(np.mean(within)) / np.sqrt(2)
        ratio = between / max(noise, 1e-6)
        print(f"rate {rate:4.0f} Hz active {active:.2f}: appetite mean {np.mean(apps):+.3f} sd {between:.3f} noise {noise:.3f} ratio {ratio:4.1f}  KC {np.mean(kcs):5.1f} Hz  fired {np.mean(fired):6.0f}  [{(time.time()-t0)/30*1000:.0f} ms/run]")
        if best is None or ratio > best[0]: best = (ratio, rate, active, apps)
ratio, rate, active, apps = best
print(f"\nbest: rate {rate} Hz, active {active}  (ratio {ratio:.1f})")
q = np.percentile(apps, [10, 25, 50, 75, 90])
print("untrained appetite percentiles 10/25/50/75/90:", np.round(q, 3))
print(f"buy threshold for ~1 page in 4 = 75th pct = {q[3]:+.3f}")
