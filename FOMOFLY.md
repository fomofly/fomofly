# fly_logic — how the fly decides

Written 2026-09-12 after the design talk. This is the whole logic of the product on one
page: three senses, one reward, one number, three rules. Everything on screen maps to a
line here. If a line here is not on the page, or the page does something not here, one of
them is wrong.

The brain behind it is the real fruit fly connectome from `fruitflydev/flycoinrh`
(165,122 neurons, 10,228,000 synapses, Janelia male CNS v1.0, CC-BY), run on our box at
`/opt/fly` with every synapse scaled to 0.3 of the paper's value so it does not seize
(measured 2026-09-11, see "What we measured" at the bottom).

## The four lines on the page

> The fly sees the meme, smells the theses, tastes the numbers. Winners smell like sugar,
> losers like a shock, and it learns which smells come with which. Appetite decides if it
> buys. Hunger decides how much. When a coin stops smelling good, it sells.

## 1. What it senses

| sense | what on the page | how it gets in | what it is honestly |
|---|---|---|---|
| **eyes** | the meme | fly taps the logo, the picture fills the phone, the 892-column retina reads brightness and contrast for 2-3 s | light and edges. A fly walks toward light, so bright and sharp is a small pleasure, dark and flat is nothing. It cannot see a dog. |
| **nose** | the theses | each thesis text → OpenAI embedding (`text-embedding-3-small`, one call per page) → frozen projection to the 53 receptor types → ORN drive | identity only. "This smells like that." The nose has no opinion. |
| **tongue** | the numbers | 1h buy share → sugar (LB3c). Top-10 concentration and sell pressure → bitter (LB1c) | the same taste line the page already shows |

The eye rule, as it runs today and stays:

```
light = (luminance − 0.22) × 2.2 + contrast × 1.6, clamped −0.6 … +1.2
```

## 2. What it learns from

**One reward: PnL.**

- When it smells a thesis, the **author's PnL** is the sugar (PAM dopamine) or the shock
  (PPL1 dopamine) paired with that smell. Strength grows with |PnL|, capped.
- When it revisits a coin it holds, its **own position PnL** is the sugar or the shock.
  This one hits harder (×2): it is the fly's own money, and it is the honest reward.

Both go into the mushroom body the way they do in a real fly: dopamine-gated **depression
only** of the KC→MBON synapses that were active during the smell. Shock depresses the
approach side, sugar depresses the avoid side. Floor at 0.25, slow recovery toward 1.0
(forgetting). Nothing else in the brain learns. The measured asymmetry stays: 27,939
reward-side synapses vs 14,349 punish-side, so it learns to like faster than to fear.
Say that on the page.

Result: the fly slowly stops liking the kind of thesis that burned it. That is the entire
intelligence.

## 3. What it decides

Everything the page did to it ends up in one number, **appetite**, −1 … +1:

```
appetite = (approach − avoid) / (approach + avoid + 2) + light
```

`approach` and `avoid` are the reward-side and punish-side MBON rates (Hz) during a 1.5 s
think after the last thesis. `light` is the eye pulse above. The panel shows one bar.

| rule | what the page says | on $10k |
|---|---|---|
| **buy** | appetite above **+0.10** after the page | untrained it buys about 1 page in 4; the threshold is tuned to that |
| **size** | **1% of balance** at the threshold, **2%** at full appetite (+0.30 and up), straight line between | appetite +0.15 → 1.25% = $125. Appetite +0.40 → 2% = $200 |
| **sell** | on a revisit, appetite below **−0.10** → sell all. Down **40%** → sell all (stop). **Profit ladder** (2026-09-12): up **10%** takes 25% of the bag, **20%** another 25%, **50%** half of the rest, **100%** half again; after each rung the stop moves to the rung below (0, +10, +20, +50), so a bag that paid once cannot go back to a loss. Checked every 20 s with the prices; a bag through a rung is visited and sold then | a $150 bag is cut at $90, halved at $300 |

(Decided 2026-09-12: 1-2% tickets, not 10%. Hunger is no longer in the size; the cash
floor does that job.)

**The operator can pin the next bid.** `python3 fly/admin.py` opens a session with the fly
(admin key, straight to the box, never through the worker): `set_next_bid 3000` makes the
next buy $3,000 whatever the appetite says (it still needs appetite above the threshold
to buy at all, and it is capped by cash); `reset` forgets it; `status` shows the pin, the
learning and the last fills. A pinned bid is spent by the first buy that uses it, then the
fly is back to 1-2%. The page logs it as the operator's, not the fly's.

`trade_now` makes the page trade the coin the fly is on (the fly's own size, or the pinned bid).

The console also sets what the page shows without a deploy: `set_ca <address> [url]` puts the
contract address in the nav chip (linked if a url is given, copy-to-clipboard if not),
`clear_ca` takes it down. The page reads `/api/fly/site` every minute.

**Many visitors.** Every visitor's page has its own fly, and each page it opens costs the box
3-5 s of single-threaded brain. The service caches a page (token + thesis ids) for 90 s so the
same page smelled by another visitor is one smell for everyone, and past three queued pages it
answers `busy`; that page then runs on the toy in the tab and the log says so. Ten visitors is
fine; a hundred means most pages come from the cache or the toy. One server-side fly that
everyone watches is the real fix, later.

**Live mode (built 2026-09-12, off by default).** The wallet is the real fomo account, read
through the gateway on the box (`fomo-api` `/account`: cash, equity, positions, fills with
explorer links) and every fill is signed and sent by the gateway (`/trade/buy`, `/trade/sell`).
The fly service sits between the page and the gateway and holds the rails: `mode` (paper or
live), the ticket floor and cap (`set_min`, `set_max`, defaults $5 and $50), one buy and one
sell per coin per ten minutes however many viewers decide the same thing, the pinned bid, and a
hard switch `FLY_LIVE=1` in `/opt/fly/.env` without which no trade is ever sent. The gateway
has its own: `FOMO_TRADING_ENABLED=true`, the exported Solana and EVM keys in its `.env`,
`FOMO_MAX_TRADE_USD` (default $5), fomo's own $2 minimum. Going live is three steps, all the
operator's: put the keys in the gateway's env and restart it, set `FLY_LIVE=1` and restart
the fly service, then `set_live` in the console (it checks the gateway can sign, and asks for
the word LIVE). `set_paper` goes back. The fomo account behind the session on 2026-09-12 was
@AwakeArmedLemur (Solana GpZy…VjJ, EVM 0xed05…1fab), $9 equity, one PONS position.

**Pictures.** Logos and profile pictures go through the worker: the edge cache first, then R2
(`fomofly-img`, fetched once ever, a year-long immutable header), then the origin. A logo
nobody has is remembered as missing so it costs one lookup, not one per visitor.

**Rig caps** (ours, labelled as ours on the page, the fly does not choose them):
max **6** open bags · never below **25%** cash · the stop and the take-profit above ·
**drawdown guard:** below **70%** of the starting balance it stops buying until the wallet
is reset · **stop watcher:** prices are marked every 20 s; a bag through the stop is
visited and sold right then, not on the next random revisit. Every fill is reported to
the box (`state/fills.jsonl`) so the ledger is not only in one browser.

**Revisits:** after a page, ~30% of the time the fly opens its profile and taps a bag. It
smells that page again (new theses, new taste, new light), thinks, and the sell rule runs.
Its own PnL on that visit is the reward (section 2).

## 4. What people see

1. Fly opens a coin, taps the meme. "measuring light…" then a number.
2. It hovers over theses. Each card glows **sweet or sour** with the brain's reaction to
   the smell (hue = margin, intensity = how strong the smell is). Not a rating. Untrained,
   every card glows about the same; after a few burns, cards that smell like the burns
   go sour. The learning is visible without a chart.
3. A taste line for the numbers.
4. The appetite bar moves during the think.
5. It taps Buy and picks the chip its appetite chose, or it leaves.
6. Later it opens a bag from its profile, smells the page again, keeps it or sells.

Log lines are readouts, not prose: `smells @handle: sweet 0.4` · `appetite +0.32 →
BUYS $TICKER $350 (hunger 70%)` · `$TICKER −41% → sold (stop)`. The fly never speaks in
the first person, and no model writes for it. If a thread needs prose it is the keeper,
third person, "the fly bought".

## 5. What is real and what is ours

| real (measured) | ours (a choice, labelled on the page) |
|---|---|
| the neurons, the wiring, the sign of every synapse | the 0.3 synapse scale (so it does not seize) |
| the eye (892 columns into L1/L2), the nose (53 receptor types), the tongue (LB taste cells) | what light means, the smell map (embedding → receptors), which numbers are sugar and bitter |
| the mushroom body and the depression-only dopamine rule | that PnL is the sugar and the shock |
| approach-side vs avoid-side MBONs, read out of the wiring | the appetite formula, the thresholds, hunger, the caps, the money |

## 6. Where it runs

- **`fly` service on the box** (`ssh form4-vps`, `/opt/fly`, FastAPI, port 8792, systemd,
  one process, one brain, learning saved to `/opt/fly/state/mb_gains.npz`). Routes:
  `POST /smell` (a page's theses + author PnLs + taste + light in; per-card glow, appetite
  out; dopamine applied), `GET /state`
  (learning stats, last decision). `OPENAI_API_KEY` lives in its `.env`, never on the page.
- **Worker:** `/api/fly/*` → `box:8792`, same shape as `/api/*` → the fomo gateway.
- **Page:** keeps its state machine, the picture tap, the sheet, the ledger. The two
  places `rig.ts` touches the toy brain for the decision (`dopamine(...)`, reading
  `mbonApproach/Avoid`) become calls to the service. The point cloud in the tab stays the
  toy until the box's real spike scatter replaces it; the model card says so.
- One fly, shared by every viewer, learning on the server.

Nothing waits on the brain: smell runs while the page's 1-2 s of fomo fetches run, so
the colours are ready before the fly reaches the first card.

## 7. Later, not today

Log every read (light, smell margin, taste, appetite) next to the position's PnL ten
minutes later. That table decides whether bright memes and sweet theses actually pay,
and replaces the hand-set weights with measured ones.

## Built 2026-09-12 (what exists, where)

- `fly/` — the service. `service.py` (FastAPI, `POST /smell`, `GET /state`), `nose.py`
  (OpenAI `text-embedding-3-small`, one call per page, frozen seed-4663 projection to the
  53 ORN groups, top 35% of groups light at up to 25 Hz), `tongue.py` (LB3c sugar, LB1c
  bitter, 20 Hz), `flysim.py` / `mushroom.py` / `build_graph.py` from flycoinrh (MIT, kept
  with LICENSE + NOTICE), `calibrate.py` (odor volume), `calibrate_think.py` (the baseline),
  `smoke.py`, `deploy/fly.service` + `deploy/sync.sh`.
- On the box: `/opt/fly`, systemd `fly`, port 8792 (ufw open), `.env` holds
  `OPENAI_API_KEY` + `FLY_API_KEY`, learning in `/opt/fly/state/mb_gains.npz`,
  ~350 MB RSS, ~3-5 s brain time per page (6 theses × 250 steps + a 500-step think).
- Worker: `/api/fly/smell|state` → `FLY_ORIGIN` (wrangler var) with `FLY_API_KEY` (secret).
  Vite dev proxies the same from `FLY_GATEWAY` + `FLY_API_KEY` in `stonk/endpoints.env`.
- Page: `app/src/fomo/fly.ts` (client + the rule constants), `rig.ts` (smell at page open,
  card dopamine from the answer, appetite/hunger/stop/take-profit in `decide()`),
  `screen.ts` (card glow in the brain's colour; the yellow word boxes are gone).

Two implementation choices on top of the design, both ours:
- **Eligibility is sparse.** Only the most active 10% of Kenyon cells during a smell may
  learn from the dopamine that follows (`KC_ELIGIBLE`). Without it every KC fires for every
  smell at this scale, and a shock would punish all smells alike. A fly's APL neuron keeps KC
  coding sparse; this stands in for it.
- **Cards have their own baseline.** A card is one thesis at full volume for 250 steps,
  a page think is the mix at half volume for 500; they score differently, so each is
  z-scored against its own naive baseline (`card_median`/`card_sd` and `median`/`sd` in
  `state/calib.json`). Before this fix every card came back sour.
- **Forgetting is per page.** `forget()` runs once per page here, not once per 12 ms step as
  in the roamer, so `recover=0.01`: a floored synapse is back to baseline in ~100 pages.
- **Appetite is a z-score.** `appetite = z / 4 + light × 0.08`, where z is the think score
  against the naive baseline (median 0.0824, sd 0.0138, measured on 40 real pages with the
  exact think procedure). The light pulse (−0.6..1.2) is scaled so it moves appetite by at
  most about ±0.1, one buy threshold, not more than the smells do.

## What we measured (2026-09-11, on the box)

- 2-core EPYC 9354P, 8 GB. One 20 ms decision = 41 ms wall, < 600 MB RAM.
- Untuned, any input drives ~47,000 neurons to the 454 Hz refractory ceiling within
  100 ms. The authors' live fly on Railway is in that state (39,352 firing, 9.5M spikes/s).
- Synapses × 0.3: 20-25k neurons active, membrane near rest, sugar reaches MN9, odors reach
  KC, PAM and both MBON sides. ORN_DA1 margin 46 vs ORN_DL3 32 at scale 0.25.
- Ten random dense odors at 0.3: margin ~50 ± 4, between-odor spread 3, KCs at 200+ Hz.
  Untrained it cannot tell theses apart; KC sparsity (lower odor rates) is the tuning job,
  and in a real fly the naive MBON output is balanced anyway — conditioning makes the bias.
