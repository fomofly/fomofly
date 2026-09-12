"""
The operator's session with the fly. Talks straight to the service (port 8792) with the
admin key; the page's worker never sees this key.

  python3 fly/admin.py                    interactive
  python3 fly/admin.py set_next_bid 3000  one command
  python3 fly/admin.py reset
  python3 fly/admin.py status

Needs FLY_GATEWAY and FLY_ADMIN_KEY in stonk/endpoints.env (source it, or this reads it).
"""
import json, os, sys, urllib.error, urllib.request
from pathlib import Path


def load_env():
    p = Path(__file__).resolve().parents[2] / "endpoints.env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def send(cmd, usd=None, **extra):
    base = os.environ["FLY_GATEWAY"].rstrip("/"); key = os.environ["FLY_ADMIN_KEY"]
    body = {"cmd": cmd, **({"usd": usd} if usd is not None else {}), **extra}
    req = urllib.request.Request(base + "/admin", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "x-admin-key": key})
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"{e.code} {e.read().decode()[:120]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def show(r):
    if not r.get("ok"):
        print("  !", r.get("error")); return
    a = r["admin"]; nb = a.get("next_bid")
    line = f"  next bid: {'$%.0f (pinned)' % nb if nb else 'its own, 1-2% by appetite'}"
    if a.get("spent"): line += f"   (last pinned ${a['spent']:.0f} spent on ${a.get('spent_on')})"
    print(line)
    site = r.get("site") or {}
    print(f"  mode: {site.get('mode', 'paper').upper()}   ticket floor ${float(site.get('minUsd', 0)):.0f} · cap ${float(site.get('maxUsd', 0)):.0f}")
    print(f"  CA on the site: {site.get('ca') or 'not launched'}" + (f"  → {site['url']}" if site.get("url") else ""))
    L = r["learning"]
    print(f"  learning: {L['depressed']:,} of {L['synapses']:,} synapses depressed, {L['rewards']} sugar / {L['punishments']} shocks, mean gain {L['mean_gain']}")
    if r.get("last"):
        print(f"  last page: ${r['last']['token']} appetite {r['last']['appetite']:+.3f} taste {r['last']['taste']}")
    for f in r.get("fills") or []:
        print(f"  fill: {f['side']} ${float(f['usd'] or 0):.0f} {f['symbol']}{' (pinned)' if f.get('pinned') else ''} appetite {f.get('appetite')}")


def run(argv):
    if not argv:
        return show(send("status"))
    cmd = argv[0]
    if cmd in ("set_next_bid", "set_bid"):
        if len(argv) < 2: print("  usage: set_bid <usd>"); return
        show(send("set_next_bid", float(argv[1])))
    elif cmd in ("set_min", "set_max"):
        if len(argv) < 2: print(f"  usage: {cmd} <usd>"); return
        show(send(cmd, float(argv[1])))
    elif cmd == "set_live":
        sure = input("  real money. type LIVE to confirm: ").strip()
        if sure != "LIVE": print("  not switched"); return
        show(send("set_live"))
    elif cmd in ("reset", "status", "clear_ca", "remove_ca", "set_paper", "trade_now"):
        show(send(cmd))
    elif cmd == "set_ca":
        if len(argv) < 2: print("  usage: set_ca <address> [url]"); return
        show(send("set_ca", ca=argv[1], url=argv[2] if len(argv) > 2 else None))
    else:
        print("  commands: trade_now · set_bid <usd> · reset · set_min <usd> · set_max <usd> · set_live · set_paper · set_ca <address> [url] · clear_ca (remove_ca) · status · quit")


if __name__ == "__main__":
    load_env()
    if len(sys.argv) > 1:
        run(sys.argv[1:]); sys.exit()
    print("fly admin. commands: trade_now · set_bid <usd> · reset · set_min <usd> · set_max <usd> · set_live · set_paper · set_ca <address> [url] · clear_ca (remove_ca) · status · quit"); show(send("status"))
    while True:
        try:
            line = input("fly> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if line in ("quit", "exit", "q"): break
        if line: run(line.split())
