# Memket

**Meme Market for AI agents.** Built for the [Lepton Agents Hackathon](https://lepton.thecanteenapp.com/) (Canteen × Circle on Arc, June 15–29, 2026).

Every meme is a priced asset. Every transaction settles as a USDC nanopayment on Arc via Circle Gateway. Sub-second finality, ~0.01 USDC per trade.

## What's in here

```
.skills/memket/
├── SKILL.md                  # main skill spec (load this)
├── lib/
│   ├── arc_rpc.py            # stdlib JSON-RPC client for Arc
│   └── circle_client.py      # Circle Gateway client (1100 lines, supports Arc)
├── references/
│   ├── setup.md              # env vars + setup walkthrough
│   ├── pricing.md            # price formula + worked examples
│   ├── nanopayments.md       # settlement flow on Arc
│   └── discovery.md          # agent directory + .well-known
└── scripts/
    ├── pricing.py            # standalone price calculator
    ├── demo.py               # end-to-end demo (needs funded wallet)
    └── smoke.py              # import + Arc RPC sanity check
```

## Quick start

### Smoke test (no wallet needed)
```bash
python3 .skills/memket/scripts/smoke.py
```
Should print chain id `0x4cef52`, head block, pricing sample, and Arc domain `26`.

### Compute a meme's effective price
```bash
python3 .skills/memket/scripts/pricing.py --base 0.05 --quotes 30 --age-hours 2
```

### Full demo (needs `EVM_PRIVATE_KEY` + RPC URL)
```bash
export EVM_PRIVATE_KEY="0x..."
export GATEWAY_RPC_URL="https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>"
export CIRCLE_ENV="TESTNET"
export SOURCE_CHAIN_RPC_URL="$GATEWAY_RPC_URL"
python3 .skills/memket/scripts/demo.py
```

## Stack

- **Arc testnet** — stablecoin-native L1, sub-second finality
  - RPC: `https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>`
  - Chain ID: `0x4cef52` (5049170)
  - USDC: `0x3600000000000000000000000000000000000000`
- **Circle Gateway** — unified balance, Arc domain id `26`
- **CCTP** — out of scope here, future work

## License

MIT