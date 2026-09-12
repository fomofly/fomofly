"""
Baseline for the think, measured exactly the way service.py runs it: a page of theses
mixed at half volume plus a typical taste, 500 steps, untrained brain. Writes
state/calib.json (median, sd) so appetite z-scores against the naive fly on real pages.
Run on the box after calibrate.py:  .venv/bin/python calibrate_think.py
"""
import json, os, random, time
import numpy as np
from flysim import FlyBrain
from mushroom import MushroomBody
from nose import Nose, embed
from tongue import Tongue
import service as S     # same constants and the same drive code

state = os.environ.get("FLY_STATE_DIR", "state")
theses = json.load(open(os.path.join(state, "calib_theses.json")))
cal = json.load(open(os.path.join(state, "calib.json")))
print(f"{len(theses)} theses; rate {cal['rate_hz']} active {cal['active']} scale {S.SCALE}")
E = embed([t["text"] for t in theses]); vec = [S.nose.receptors(e) for e in E]
by = {}
for i, t in enumerate(theses): by.setdefault(t["token"], []).append(i)
rng = random.Random(3); scores = []
tastes = [{"buys": 14, "sells": 5, "top10": 22}, {"buys": 8, "sells": 8, "top10": 35}, {"buys": 3, "sells": 12, "top10": 55}, {"buys": 10, "sells": 4, "top10": 15}]
t0 = time.time()
for rep in range(40):
    tok = rng.choice(list(by)); idx = rng.sample(by[tok], min(len(by[tok]), rng.randint(3, 6)))
    mix = np.mean([vec[i] for i in idx], axis=0) * 0.5
    drive = S.merge(S.nose.drive(mix), S.tongue.drive(rng.choice(tastes)))
    out = S.fb.run(drive, S.THINK_STEPS, record=S.REC, seed=rep)
    s, ap, av = S.score(out); scores.append(s)
    if rep % 10 == 0: print(f"  page {rep}: score {s:+.4f} ap {ap:.0f} av {av:.0f} fired {len(out['_fired'])}")
# and the same for one card: a single thesis at full volume plus taste, SMELL_STEPS
cards = []
for rep in range(40):
    i = rng.randrange(len(theses))
    out = S.fb.run(S.merge(S.nose.drive(vec[i]), S.tongue.drive(rng.choice(tastes))), S.SMELL_STEPS, record=S.REC, seed=100 + rep)
    cards.append(S.score(out)[0])
cards = np.array(cards)
print(f"card baseline: median {np.median(cards):+.4f} sd {cards.std():.4f}")
cal.update({"card_median": round(float(np.median(cards)), 4), "card_sd": round(float(cards.std()), 4)})
scores = np.array(scores)
med, sd = float(np.median(scores)), float(scores.std())
q = np.percentile(scores, [10, 25, 50, 75, 90])
print(f"think baseline: median {med:+.4f} sd {sd:.4f} pct10/25/50/75/90 {np.round(q, 4)} [{(time.time()-t0)/40*1000:.0f} ms/think]")
cal.update({"median": round(med, 4), "sd": round(sd, 4), "measured": f"think baseline {time.strftime('%Y-%m-%d')}: 40 real pages mixed at 0.5 + taste, untrained, {S.THINK_STEPS} steps"})
json.dump(cal, open(os.path.join(state, "calib.json"), "w"), indent=1); print("wrote", cal)
