"""
The nose: a thesis becomes a smell.

A fly smells with 2,635 olfactory receptor neurons in 53 groups, one per receptor
type (ORN_DA1, ORN_DL3, ...). A smell is just which groups fire, how hard. We turn a
thesis into that: OpenAI embeds the text (1536 numbers, no opinion in them), a fixed
random matrix chosen once folds those into 53 numbers in 0..1, and number k is how
hard receptor group k fires. Similar text -> similar receptors -> the same Kenyon
cells light up. Nobody rates the thesis. Nobody says "bullish".

The matrix is seeded, so the same thesis smells the same tomorrow and on another box.
"""
import hashlib
import json
import os
import re
import time
import urllib.request

import numpy as np

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIMS = 1536
PROJ_SEED = 4663          # Robinhood Chain's id, why not; it never changes


def embed(texts, key=None, base=None, timeout=30):
    """One call for a whole page of theses. Returns (n, 1536) float32."""
    key = key or os.environ["OPENAI_API_KEY"]
    base = (base or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    texts = [(t or "").strip()[:2000] or "." for t in texts]
    req = urllib.request.Request(
        base + "/embeddings",
        data=json.dumps({"model": EMBED_MODEL, "input": texts}).encode(),
        headers={"Authorization": "Bearer " + key, "content-type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    out = np.zeros((len(texts), EMBED_DIMS), dtype=np.float32)
    for d in r["data"]:
        out[d["index"]] = d["embedding"]
    return out


class Nose:
    def __init__(self, fb, rate_hz=20.0, active=0.35):
        """
        fb       the FlyBrain (for the ORN groups)
        rate_hz  the loudest a receptor group fires
        active   share of the 53 groups a smell may light; the rest stay quiet, so
                 Kenyon cells stay sparse the way a fly's do
        """
        T = np.asarray(fb.types).astype(str)
        orn = np.flatnonzero(np.char.startswith(T, "ORN_"))
        self.groups = sorted(set(T[orn]))                       # 53 receptor types
        self.idx = {g: np.flatnonzero(T == g) for g in self.groups}
        rng = np.random.default_rng(PROJ_SEED)
        self.R = rng.standard_normal((EMBED_DIMS, len(self.groups))).astype(np.float32)
        self.rate_hz = rate_hz
        self.active = active
        self.cache = {}                                          # thesis id -> 53 rates

    def receptors(self, e):
        """1536 -> 53 numbers in 0..1. Top `active` share of groups light, rest 0."""
        z = e @ self.R
        z = (z - z.mean()) / (z.std() + 1e-6)
        k = max(1, int(round(self.active * len(self.groups))))
        cut = np.sort(z)[-k]
        v = np.where(z >= cut, z, -np.inf)
        v = 1.0 / (1.0 + np.exp(-v))                             # sigmoid, 0 where cut
        return np.nan_to_num(v, nan=0.0, neginf=0.0).astype(np.float32)

    def smells(self, items):
        """items: [{id, text}] -> {id: 53-vector}. Embeds only what is not cached."""
        need = [it for it in items if it["id"] not in self.cache]
        if need:
            E = embed([it["text"] for it in need])
            for it, e in zip(need, E):
                self.cache[it["id"]] = self.receptors(e)
            if len(self.cache) > 5000:
                for k in list(self.cache)[:1000]:
                    del self.cache[k]
        return {it["id"]: self.cache[it["id"]] for it in items}

    def drive(self, v):
        """53 receptor levels -> {neuron indices: Hz} for FlyBrain.run."""
        return {tuple(self.idx[g]): float(self.rate_hz * x)
                for g, x in zip(self.groups, v) if x > 0.0}

    def intensity(self, v):
        return float(np.clip(v.sum() / max(1, int(self.active * len(self.groups))), 0, 1))
