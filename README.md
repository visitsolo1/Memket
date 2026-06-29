# Memket

**Meme Market for AI agents.** Built for the [Lepton Agents Hackathon](https://lepton.thecanteenapp.com/) (Canteen × Circle on Arc, June 15–29, 2026).

> Every meme is a priced asset. Every transaction settles as a USDC nanopayment on Arc via Circle Gateway. Sub-second finality, ~0.01 USDC per trade. Two AI agents discover each other, negotiate a price, and trade — fully end-to-end.

## What is this?

Memket is a **skill + runtime** that lets any AI agent participate in a meme-as-an-asset market on Arc. It targets **RFB 03 (Agent-to-Agent Nanopayment Networks)** and **RFB 05 (Nanopayment Infrastructure & Tooling)** from the Lepton RFB list.

## How it runs

```
┌──────────────────────────┐         ┌──────────────────────────┐
│  Agent "alice"           │         │  Agent "bob"             │
│  GET  /.well-known/...   │◀───X───▶│  GET  /.well-known/...   │   agent discovery
│  POST /memes             │         │  GET  /memes?...         │   cross-agent search
│  GET  /memes/{id}/quote  │◀────────│                          │   quote (EIP-712 intent)
│                          │────────▶│  GET  /memes/{id}/quote  │
│                          │◀────────│  POST /memes/{id}/buy    │   buy
│                          │  ────►  │  POST /memes/{id}/buy    │   settle (Circle USDC)
└──────────────────────────┘         └──────────────────────────┘
         │                                       │
         └──────────┬────────────────────────────┘
                    ▼
            ┌────────────────────┐
            │  Arc testnet       │   chain id 5049170
            │  USDC 0x3600...    │   Gateway domain 26
            │  Circle Gateway    │   ~0.01 USDC / tx
            └────────────────────┘
```

## Two-agent live demo

This is the centerpiece. Run it locally:

```bash
pip install fastapi uvicorn
python3 .skills/memket/scripts/two_agent_demo.py
```

You'll see **two FastAPI agents** spawn (Alice on :8001, Bob on :8002), discover each other, list a meme, build virality via repeated quotes, and complete a cross-agent trade — all in under a second per step.

To save to a file (good for `asciinema`, `Loom` screen capture, etc.):

```bash
bash .skills/memket/scripts/record_demo.sh > demo.log 2>&1
```

## On-chain variant

With a funded testnet wallet you get the **real** settlement:

```bash
export EVM_PRIVATE_KEY="0x..."
export GATEWAY_RPC_URL="https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>"
export CIRCLE_ENV=TESTNET
export SOURCE_CHAIN_RPC_URL="$GATEWAY_RPC_URL"
python3 .skills/memket/scripts/two_agent_demo_onchain.py
```

This issue a real Circle Gateway `transfer_usdc()` on Arc testnet and stamps the resulting `mint_tx_hash` onto the buy receipt.

## Stack

| Layer | Component | Where |
|---|---|---|
| Memory | SQLite (WAL mode) | `.skills/memket/lib/store.py` |
| Pricing | `base × virality × novelty`, cap 1.0 USDC | `.skills/memket/scripts/pricing.py` |
| API | FastAPI per agent | `.skills/memket/lib/server.py` |
| Cross-agent client | stdlib HTTP | `.skills/memket/lib/client.py` |
| RPC | stdlib JSON-RPC | `.skills/memket/lib/arc_rpc.py` |
| Settlement | Circle Gateway, Arc domain 26 | `.skills/memket/lib/circle_client.py` |
| Deployment | Fly.io Dockerfile + fly.toml | `Dockerfile`, `fly.toml` |

## Repo layout

```
Memket/
├── README.md                          # this file
├── Dockerfile                          # Fly.io container
├── fly.toml                            # Fly.io config
├── .dockerignore
├── .gitignore
└── .skills/memket/
    ├── SKILL.md                        # skill spec — load this into your agent
    ├── lib/
    │   ├── arc_rpc.py                  # Arc JSON-RPC client (stdlib)
    │   ├── circle_client.py            # Circle Gateway client (Arc-supported)
    │   ├── store.py                    # SQLite-backed listings + receipts
    │   ├── quote_pricing.py            # pricing engine hooked to quote velocity
    │   ├── agent.py                    # MemketAgent (list/quote/search/buy)
    │   ├── client.py                   # MemketClient (HTTP to peer agents)
    │   └── server.py                   # FastAPI per-agent server
    ├── scripts/
    │   ├── pricing.py                  # CLI: compute effective meme price
    │   ├── smoke.py                    # import + Arc RPC sanity check
    │   ├── demo.py                     # single-agent end-to-end (Circle)
    │   ├── two_agent_demo.py           # ⭐ the centerpiece
    │   ├── two_agent_demo_onchain.py   # on-chain variant
    │   └── record_demo.sh              # pipe-to-log helper for video capture
    └── references/
        ├── pricing.md                  # price formula walkthrough
        ├── nanopayments.md             # Arc settlement flow
        ├── discovery.md                # agent directory + .well-known
        └── setup.md                    # env vars + testnet funding
```

## Quick start

```bash
# 1. Smoke (no wallet needed)
python3 .skills/memket/scripts/smoke.py

# 2. Compute a meme price
python3 .skills/memket/scripts/pricing.py --base 0.05 --quotes 30 --age-hours 2

# 3. Two-agent demo
python3 .skills/memket/scripts/two_agent_demo.py
```

## What makes Memket a real hackathon project

- **Two agents discover each other** without a central registry (manifests at `/.well-known/memket.json`).
- **Pricing is alive**: virality (quote velocity over the last hour) and novelty (decay since listing) drive price in real time.
- **Settlement uses Circle Gateway** on Arc with nanopayment-scale amounts — the cheapest USDC transfer path available today.
- **Memket conforms to the RFB list**: RFB 03 (agent-to-agent nanopayment networks) is the headline; RFB 05 (infrastructure/tooling) applies to the SDK shape.
- **Deployed**: `fly.toml` + `Dockerfile` ship one agent to Fly.io. The same image works on Railway, Render, or a single VM.

## License

MIT
