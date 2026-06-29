"""Memket pricing engine — pulls quote velocity from the store.

We expose price_for_meme(...) by composing the calc from scripts/pricing.py.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

# Make sibling modules importable
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "..", "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from store import Store  # noqa: E402
import pricing as _pricing_calc  # noqa: E402


def quote_for_meme(store: Store, meme_id: str, base_price: str) -> dict[str, Any]:
    """Compute a live quote for the given meme.

    base_price is a USDC string (e.g. "0.04"). Quotes_last_hour is read from
    the store so popularity actually drives the price.
    """
    meme = store.get_meme(meme_id)
    if meme is None:
        raise ValueError(f"meme not found: {meme_id}")
    quotes_last_hour = store.count_recent_quotes(meme_id, within_seconds=3600)
    age_hours = max(0.0, (time.time() - meme.listed_at) / 3600.0)
    inp = _pricing_calc.PriceInputs(
        base_price=float(base_price),
        quotes_last_hour=quotes_last_hour,
        hours_since_listed=age_hours,
    )
    price = _pricing_calc.effective_price(inp)
    spread = _pricing_calc.spread_bps(age_hours)
    return {
        "meme_id": meme_id,
        "base_price_usdc": base_price,
        "effective_price_usdc": f"{price:.6f}",
        "spread_bps": spread,
        "quotes_last_hour": quotes_last_hour,
        "age_hours": round(age_hours, 4),
    }
