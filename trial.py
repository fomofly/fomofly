"""
Does it make good calls? Run real fomo pages through the live service and show what the
page would do with them: appetite, buy or pass, the ticket on a $1,000 paper wallet.
On the box:  set -a; . .env; set +a; FOMO_API_KEY=... .venv/bin/python trial.py
"""
import json, os, sys, time, urllib.request
GW = os.environ.get("FOMO_GATEWAY", "http://127.0.0.1:8791").rstrip("/"); FK = os.environ["FOMO_API_KEY"]
FLY = os.environ.get("FLY_URL", "http://127.0.0.1:8792"); KEY = os.environ["FLY_API_KEY"]
BUY_AT, MIN_PCT, MAX_PCT, FULL, CASH_FLOOR = 0.10, 0.01, 0.02, 0.30, 0.25
def gw(path, body=None):
    req = urllib.request.Request(GW + path, data=json.dumps(body).encode() if body else None, headers={"x-api-key": FK, "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))
def smell(body):
    req = urllib.request.Request(FLY + "/smell", data=json.dumps(body).encode(), headers={"x-api-key": KEY, "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))
# the same reading list the page uses: what the 24h leaderboard holds
lb = gw("/leaderboard/24h")["leaderboard"][:25]; agg = {}
for u in lb:
    for h in u.get("topHoldings") or []:
        k = f'{h["tokenAddress"]}:{h["networkId"]}'; a = agg.setdefault(k, {"address": h["tokenAddress"], "networkId": h["networkId"], "n": 0}); a["n"] += 1
toks = sorted(agg.values(), key=lambda a: -a["n"])[:int(sys.argv[1]) if len(sys.argv) > 1 else 12]
usdc = equity = 1000.0; bags = 0; rows = []
for t in toks:
    tid = f'{t["address"]}:{t["networkId"]}'
    try:
        st = gw("/tokens/filter", {"tokens": [tid]}); sym = (st[0] if isinstance(st, list) and st else {}).get("symbol") or (st.get("results", [{}])[0].get("symbol") if isinstance(st, dict) else None) or t["address"][:6]
    except Exception: sym = t["address"][:6]
    try: det = gw("/tokens/details/" + tid)
    except Exception: det = {}
    th = gw(f'/feed/token/thesis?tokenAddress={t["address"]}&networkId={t["networkId"]}').get("items") or []
    theses = [{"id": str(i["id"]), "text": " ".join(str(i["comment"]["comment"]).split()), "pnlPct": (float(i["authorTrade"].get("percentageUnrealizedPnl") or 0) if i.get("authorTrade") and not i["authorTrade"].get("closedAt") else None)} for i in th if i.get("type") == "thesis" and (i.get("comment") or {}).get("comment")][:6]
    feed = gw(f'/feed/token?tokenAddress={t["address"]}&networkId={t["networkId"]}').get("items") or []
    buys = sum(1 for i in feed if i.get("type") == "swap_buy"); sells = sum(1 for i in feed if i.get("type") == "swap_sell")
    taste = {"buys": buys, "sells": sells, "top10": float(det.get("top10HoldersPercent") or 0)}
    if not theses: print(f"{sym:<10} no theses, the fly leaves"); continue
    r = smell({"token": {"symbol": sym, "address": t["address"]}, "theses": theses, "taste": taste, "light": 0.0, "ownPnl": None})
    ap = r["appetite"]; hunger = usdc / equity
    greens = sum(1 for x in theses if (x["pnlPct"] or 0) > 1); reds = sum(1 for x in theses if (x["pnlPct"] or 0) < -1)
    act = "pass"
    if ap > BUY_AT:
        pct = MIN_PCT + (MAX_PCT - MIN_PCT) * max(0.0, min(1.0, (ap - BUY_AT) / (FULL - BUY_AT)))
        usd = min(pct * equity, usdc - CASH_FLOOR * equity)
        if bags >= 6: act = "veto (6 bags)"
        elif usd < 1: act = "veto (no cash)"
        else: act = f"BUY {pct*100:.1f}% = ${usd:.0f}"; usdc -= usd; bags += 1
    sweet = [c["sweet"] for c in r["cards"]]
    print(f"{sym:<10} {len(theses)} theses (authors {greens} green / {reds} red)  taste {r['taste']:<6} cards {' '.join(f'{s:+.2f}' for s in sweet):<40} appetite {ap:+.3f} z {r['z']:+.2f}  -> {act}   [{r['ms']} ms]")
    rows.append((sym, ap, act))
print(f"\n{len(rows)} pages: {sum(1 for _,a,_ in rows if a > BUY_AT)} would buy, cash left ${usdc:.0f} of $1000, {bags} bags; learning {r['learning']['depressed']} synapses depressed, {r['learning']['rewards']} sugar / {r['learning']['punishments']} shocks so far")
