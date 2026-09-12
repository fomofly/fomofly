"""
The tongue: the numbers on the page become taste.

LB3c cells on the mouth fire for sugar, LB1c for bitter (the labels are the dataset's,
the assignment sugar/bitter was found by stimulating each and watching MN9, the eat
neuron - see the flycoin validate table). We feed them the page's numbers:
  sugar  = share of buys in the last hour            (buys / (buys + sells))
  bitter = how much the top 10 wallets hold          (top10 / 100)
"""
import numpy as np


class Tongue:
    def __init__(self, fb, rate_hz=20.0):
        T = np.asarray(fb.types).astype(str)
        self.sugar = np.flatnonzero(T == "LB3c")
        self.bitter = np.flatnonzero(T == "LB1c")
        self.rate_hz = rate_hz

    def drive(self, taste):
        """taste: {buys, sells, top10} -> {neuron indices: Hz}. Missing numbers = flat."""
        if not taste:
            return {}
        b, s = float(taste.get("buys") or 0), float(taste.get("sells") or 0)
        sweet = b / (b + s) if (b + s) > 0 else 0.5
        sour = min(1.0, max(0.0, float(taste.get("top10") or 0) / 100.0))
        out = {}
        if sweet > 0:
            out[tuple(self.sugar)] = self.rate_hz * sweet
        if sour > 0:
            out[tuple(self.bitter)] = self.rate_hz * sour
        return out

    @staticmethod
    def word(taste):
        if not taste:
            return "flat"
        b, s = float(taste.get("buys") or 0), float(taste.get("sells") or 0)
        sweet = b / (b + s) if (b + s) > 0 else 0.5
        return "sweet" if sweet >= 0.6 else "bitter" if sweet <= 0.4 else "flat"
