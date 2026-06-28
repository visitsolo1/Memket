#!/usr/bin/env python3
"""Compute the effective Memket price for a meme.

Usage:
    python3 pricing.py --base 0.05 --quotes 30 --age-hours 2
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass
class PriceInputs:
    base_price: float
    quotes_last_hour: int
    hours_since_listed: float


def virality(quotes_last_hour: int) -> float:
    return 1.0 + min(quotes_last_hour / 10.0, 4.0)


def novelty(hours_since_listed: float) -> float:
    return 1.0 / (1.0 + hours_since_listed / 24.0)


def effective_price(inp: PriceInputs) -> float:
    raw = inp.base_price * virality(inp.quotes_last_hour) * novelty(inp.hours_since_listed)
    return max(0.001, min(raw, 1.0))


def spread_bps(hours_since_listed: float) -> int:
    return int(round(200 * (1.0 - novelty(hours_since_listed))))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=float, required=True, help="base price USDC")
    p.add_argument("--quotes", type=int, default=0, help="quotes in last hour")
    p.add_argument("--age-hours", type=float, required=True, help="hours since listed")
    args = p.parse_args()

    inp = PriceInputs(args.base, args.quotes, args.age_hours)
    price = effective_price(inp)
    spread = spread_bps(args.age_hours)
    print(f"effective_price_usdc={price:.6f}")
    print(f"spread_bps={spread}")


if __name__ == "__main__":
    main()