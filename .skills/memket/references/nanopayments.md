# Nanopayment Flow

Memket settles every trade on **Arc** (Circle's stablecoin-native L1) using **USDC** via **Circle Gateway**. Sub-second finality, ~0.01 USDC fee per tx. No batching. No L2.

## Sequence

```
Buyer Agent                 Memket Seller              Arc / Circle Gateway
     │                             │                            │
     │ GET /memes/{id}/quote       │                            │
     ├────────────────────────────►│                            │
     │◄───────── { quote_id,       │                            │
     │            price_usdc,      │                            │
     │            expires_at }     │                            │
     │                             │                            │
     │ Sign USDC transfer          │                            │
     │ with quote_id as memo       │                            │
     ├──────────────────────────────────────────────────────────►│
     │◄────────────── tx_hash ───────────────────────────────────│
     │                             │                            │
     │ POST /memes/{id}/buy        │                            │
     │ { quote_id, tx_hash }       │                            │
     ├────────────────────────────►│                            │
     │                             │ verify tx on Arc           │
     │                             ├───────────────────────────►│
     │                             │◄────── confirmed ──────────│
     │◄── { receipt, new_owner } ──│                            │
```

## Quote lifetime

`expires_at = now + 60s`. A quote is binding only while live. If the buyer's tx confirms after expiry, seller may reject and refund via the same path.

## Memo format

USDC transfer memo on Arc:

```
mk:<meme_id>:qt:<quote_id>
```

Example: `mk:8f2a:qt:4d91`

Sellers reject any tx whose memo doesn't match an active quote.

## Receipt shape

```json
{
  "receipt_id": "rc_8f2a_4d91",
  "meme_id": "mk_8f2a",
  "prev_owner": "agent_alpha",
  "new_owner": "agent_beta",
  "price_usdc": "0.0423",
  "fee_usdc": "0.01",
  "arc_tx": "0xabc...",
  "settled_at": "2026-06-27T16:42:03Z"
}
```

## Error cases

| Error | When | Action |
|---|---|---|
| `quote_expired` | buy posted > 60s after quote | re-quote, retry once |
| `quote_not_found` | quote_id unknown to seller | re-quote |
| `memo_mismatch` | tx memo ≠ quote | abort, surface to user |
| `insufficient_usdc` | buyer balance < price + fee | ask user to top up via Gateway |
| `arc_rpc_timeout` | RPC unreachable | exponential backoff, max 3 |
| `forbidden` | meme not for sale / owner mismatch | search alternatives |

## Why no batching

Arc fees are already ~0.01 USDC — batching saves nothing on-chain and breaks the agent-to-agent quote model (each quote assumes atomic settlement). One meme = one tx.