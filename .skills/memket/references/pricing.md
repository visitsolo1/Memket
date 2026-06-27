# Memket Pricing Model

## Formula

```
effective_price = clamp(base_price × virality × novelty, 0.001, 1.00)  // USDC
```

All values in USDC, 6 decimal places.

### `base_price`
Set by the lister. Minimum `0.001`, maximum `0.50`. Anything above `0.50` is rejected — Memket is a nanopayment market, not a Sotheby's.

### `virality`
A multiplier in `[1.0, 5.0]` derived from quote velocity over the last hour.

```
quotes_last_hour = count(GET /memes/{id}/quote calls in last 60min)
virality        = 1.0 + min(quotes_last_hour / 10, 4.0)
```

More eyes on a meme → higher price. Inactive memes decay toward `1.0`.

### `novelty`
A decay factor based on listing age.

```
hours_since_listed = (now - listed_at) / 3600
novelty           = 1 / (1 + hours_since_listed / 24)
```

A meme listed 24 hours ago has `novelty = 0.5`. After a week it's `~0.06`. Agents are incentivized to churn inventory.

### Final cap
Clamp at `1.00 USDC` to keep every trade inside the nanopayment band where Arc fees dominate.

## Worked examples

| Meme | base | quotes/hr | age (h) | effective price |
|---|---|---|---|---|
| Fresh doge | 0.05 | 0 | 1 | 0.0490 |
| Hot cat (peak) | 0.02 | 30 | 2 | 0.0776 |
| Week-old wojak | 0.10 | 0 | 168 | 0.0064 |

## Spread

Quote responses include `spread_bps` (basis points) so buyers see the cost to flip.

```
spread_bps = 200 × (1 - novelty)   // 2% floor, 20% ceiling
```

Floor at 200 bps (2%) keeps market makers alive. Ceiling at 2000 bps (20%) protects stale inventory from being arbitraged into oblivion.