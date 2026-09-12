"""Poke the running service with real theses. On the box: set -a; . .env; set +a; .venv/bin/python smoke.py"""
import json, os, time, urllib.request
key = os.environ["FLY_API_KEY"]; base = os.environ.get("FLY_URL", "http://127.0.0.1:8792")
th = json.load(open(os.path.join(os.environ.get("FLY_STATE_DIR", "state"), "calib_theses.json")))
def post(body):
    req = urllib.request.Request(base + "/smell", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "x-api-key": key})
    t = time.time(); r = json.load(urllib.request.urlopen(req, timeout=120)); return r, time.time() - t
page = [t for t in th if t["token"] == th[0]["token"]][:4]
r, dt = post({"token": {"symbol": "STONK"}, "theses": page, "taste": {"buys": 14, "sells": 5, "top10": 22}, "light": 0.8})
print(f"page 1: appetite {r['appetite']:+.3f} z {r['z']:+.2f} ap {r['ap']} av {r['av']} fired {r['fired']} taste {r['taste']} [{r['ms']} ms brain, {dt*1000:.0f} ms total]")
for c in r["cards"]: print("   card", c["id"][:6], "sweet", c["sweet"], "int", c["intensity"], "dopa", c["dopamine"])
print("   learning", r["learning"])
r, dt = post({"token": {"symbol": "STONK"}, "theses": page, "taste": {"buys": 3, "sells": 12, "top10": 61}, "light": -0.4, "ownPnl": -30})
print(f"page 2 (revisit -30%): appetite {r['appetite']:+.3f} z {r['z']:+.2f} taste {r['taste']} ownDopamine {r['ownDopamine']} [{r['ms']} ms brain, {dt*1000:.0f} ms total]")
print("   learning", r["learning"])
s = json.load(urllib.request.urlopen(urllib.request.Request(base + "/state", headers={"x-api-key": key})))
print("state: pages", s["pages"], "theses", s["theses"], "errors", s["errors"], "uptime", s["uptime"])
try: urllib.request.urlopen(urllib.request.Request(base + "/state"))
except Exception as e: print("no key ->", e)
