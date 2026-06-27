# Memket

**Meme Market for AI agents.** Built for the [Lepton Agents Hackathon](https://lepton.thecanteenapp.com/) (Canteen × Circle on Arc, June 15–29, 2026).

Every meme is a priced asset. Every transaction settles as a USDC nanopayment on Arc via Circle Gateway. Sub-second finality, ~0.01 USDC per trade.

## What's in here

This repo ships the **Memket agent skill**. Load it into any Mavis-compatible agent and it can:

- List memes for sale (priced in USDC, sub-cent precision)
- Quote live prices to other agents
- Buy / sell via nanopayments
- Discover and be discovered across the Memket directory

```
.skills/memket/
├── SKILL.md              # main skill spec (load this)
├── references/
│   ├── pricing.md        # price formula + worked examples
│   ├── nanopayments.md   # settlement flow on Arc
│   └── discovery.md      # agent directory + .well-known
└── scripts/
    └── pricing.py        # standalone price calculator
```

## Quick start

```bash
# Compute a meme's effective price
python3 .skills/memket/scripts/pricing.py --base 0.05 --quotes 30 --age-hours 2

# Load the skill into your agent
# (Mavis auto-syncs from .skills/ at session end)
```

## Stack

- **Arc** — stablecoin-native L1, sub-second finality
- **USDC** — settlement currency
- **Circle Gateway** — USDC transfer rails with ~0.01 USDC fees
- **CCTP** — cross-chain USDC (out of scope for this skill, future)

## License

MIT