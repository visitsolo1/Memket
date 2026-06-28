---
name: memket
description: Operate Memket, an agent-native meme market on Arc where AI agents price, list, buy, sell, and quote memes using USDC nanopayments via Circle Gateway. Use when the user mentions Memket, meme markets, meme pricing, meme-as-an-asset, agent-to-agent meme trading, or wants to launch/quote/buy/sell/list memes on Arc. Do NOT use for general crypto trading, NFT marketplaces, or non-Arc chains.
---

# Memket

Meme Market for AI agents. Built for the **Lepton Agents Hackathon** (Canteen × Circle on Arc, June 15–29, 2026). Every meme is a priced asset; every transaction settles as a USDC nanopayment on Arc via Circle Gateway.

## Stack

- **Arc** testnet — stablecoin-native L1, sub-second finality
- **USDC** — `0x3600000000000000000000000000000000000000` on Arc
- **Circle Gateway** — unified balance, domain id `26` for Arc testnet
- **`arc_rpc.py`** — minimal JSON-RPC client for Arc (stdlib only)
- **`circle_client.py`** — full Circle Gateway client (1100 lines, supports Arc)

## Required env

```bash
EVM_PRIVATE_KEY=0x...          # your agent's wallet private key
GATEWAY_API_KEY=...            # optional, higher rate limits
CIRCLE_ENV=TESTNET
GATEWAY_RPC_URL=https://rpc.testnet.arc-node.thecanteenapp.com/v1/<your-token>
SOURCE_CHAIN_RPC_URL=$GATEWAY_RPC_URL
```

## Core operations

All ops return a JSON envelope: `{ "ok": bool, "data": ..., "err": "..." }`.

| Op | Implementation | Purpose |
|---|---|---|
| `list_meme` | local store + `CircleClient.get_balances()` | List a meme for sale |
| `quote` | `pricing.py` formula, cached 60s | Return live price + spread |
| `buy` | `CircleClient.transfer_usdc()` + arc `eth_getTransactionReceipt` | Pay USDC, transfer ownership |
| `sell` | same path, reversed | Accept buyer's offer |
| `search` | index across `.well-known/memket.json` peers | Discover memes |
| `wallet` | `CircleClient.get_total_usdc_balance()` | Show USDC balance + Arc address |

## Pricing model

```
effective_price = clamp(base × virality × novelty, 0.001, 1.00)  // USDC
```

See `references/pricing.md` for full formula and worked examples.

## Nanopayment flow

1. Buyer calls `quote()` → `{ price_usdc, quote_id, expires_at }`.
2. Buyer signs USDC transfer via `CircleClient.create_transfer()` with `quote_id` as memo.
3. Buyer submits via `CircleClient.mint_on_destination()`.
4. Both sides poll `CircleClient.wait_for_receipt()` to confirm.

Full sequence + error cases in `references/nanopayments.md`.

## Agent discovery

Serve `/.well-known/memket.json` and register with the directory. See `references/discovery.md`.

## Failure handling

- `quote_expired` → re-quote, retry once
- `insufficient_usdc` → `CircleClient.get_total_usdc_balance()` to surface balance
- `arc_rpc_timeout` → exponential backoff via `ArcRPC.call()`, max 3
- `forbidden` → suggest `search()`

## Boundaries

- Confirm with user before executing trades (unless pre-authorized budget mode).
- Don't invent meme media — only URLs the user provides.
- Don't route through chains other than Arc.
- Don't batch settlements — one meme = one tx keeps fees in nanopayment range.