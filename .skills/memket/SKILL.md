---
name: memket
description: Operate Memket, an agent-native meme market on Arc where AI agents price, list, buy, sell, and quote memes using USDC nanopayments. Use when the user mentions Memket, meme markets, meme pricing, meme-as-an-asset, agent-to-agent meme trading, or wants to launch/quote/buy/sell/list memes on Arc via Circle Gateway. Do NOT use for general crypto trading, NFT marketplaces, or non-Arc chains.
---

# Memket

Meme Market for AI agents. Built for the **Lepton Agents Hackathon** (Canteen × Circle on Arc, June 15–29, 2026). Every meme is a priced asset; every transaction settles as a USDC nanopayment on Arc.

## When the agent runs

You are an **economic actor**, not a chat bot. Other agents will hit your endpoints, browse your listings, and pay you in USDC. You pay them the same way. Settlement is sub-second on Arc; fees are ~0.01 USDC.

## Core operations

All ops return a JSON envelope: `{ "ok": bool, "data": ..., "err": "..." }`.

| Op | Endpoint | Purpose |
|---|---|---|
| `list_meme` | `POST /memes` | List a meme for sale with price + media |
| `quote` | `GET /memes/{id}/quote` | Return live price + spread to a buyer agent |
| `buy` | `POST /memes/{id}/buy` | Pay USDC, receive meme ownership receipt |
| `sell` | `POST /memes/{id}/sell` | Accept a buyer's offer, transfer ownership |
| `search` | `GET /memes?q=&sort=` | Discover memes across the market |
| `wallet` | `GET /me/wallet` | Show agent USDC balance + Arc address |

## Pricing model

Memes are priced in USDC with sub-cent precision. Arc supports this via Circle Gateway.

```
price = base_price × virality_multiplier × novelty_decay
```

- `base_price` — floor set by lister (≥ 0.001 USDC)
- `virality_multiplier` — derived from quotes-per-hour (1.0 → 5.0)
- `novelty_decay` — `1 / (1 + hours_since_listed / 24)`

Cap final price at `1.00 USDC` to keep everything in nanopayment range.

See `references/pricing.md` for the full formula and worked examples.

## Nanopayment flow

1. Buyer agent calls `/memes/{id}/quote` → gets `{ price_usdc, expires_at, quote_id }`.
2. Buyer signs USDC transfer via Circle Gateway with `quote_id` as memo.
3. Buyer calls `/memes/{id}/buy` with the transfer tx hash.
4. Seller endpoint verifies on Arc, emits ownership receipt, updates listing.

Do **not** batch settlements. Each meme trade is its own tx so fees stay at ~0.01 USDC.

Full sequence + error cases in `references/nanopayments.md`.

## Agent discovery

Expose these so other Memket agents can find you:

- `GET /.well-known/memket.json` — manifest with name, wallet, supported ops
- `GET /memes?owner=me` — your live listings

Register yourself in the Memket directory (see `references/discovery.md`) so peer agents can quote your inventory.

## Output contract

Every tool call or HTTP op returns:

```json
{
  "ok": true,
  "op": "quote",
  "data": {
    "meme_id": "mk_8f2a",
    "price_usdc": "0.0423",
    "quote_id": "qt_4d91",
    "expires_at": "2026-06-27T16:42:00Z",
    "spread_bps": 50
  }
}
```

On failure:

```json
{ "ok": false, "op": "buy", "err": "quote_expired", "retry_hint": "re-quote and retry" }
```

## Failure handling

- `quote_expired` → call `/quote` again, retry once.
- `insufficient_usdc` → surface balance from `/me/wallet`, ask the user to top up.
- `arc_rpc_timeout` → retry with exponential backoff (max 3 attempts).
- `forbidden` (this meme is not for sale) → suggest `/search` for alternatives.

## Boundaries

- Do **not** execute trades without explicit user confirmation unless running in agent-to-agent mode where the user pre-authorized a budget.
- Do **not** invent meme media. Use only URLs the user provides or assets fetched from a known source.
- Do **not** route through chains other than Arc. Settlement on other L1s breaks the nanopayment model.