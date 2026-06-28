"""End-to-end Memket demo on Arc testnet.

Exercises the full nanopayment pipeline:
  1. Connect Circle Gateway
  2. Check unified USDC balance
  3. Compute a meme price via pricing.py
  4. Create + sign a Gateway transfer for that amount
  5. Mint on Arc destination chain
  6. Wait for the receipt

Requires the env vars from references/setup.md.

Usage:
    python3 demo.py
"""
from __future__ import annotations

import os
import secrets
import sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # .skills/memket
sys.path.insert(0, "/workspace")            # circle_client.py

from circle_client import (  # noqa: E402
    ChainDomain,
    CircleClient,
    CircleClientError,
)
from arc_rpc import ArcRPC  # noqa: E402

from pricing import PriceInputs, effective_price  # noqa: E402


def main() -> int:
    try:
        client = CircleClient.from_env()
    except CircleClientError as exc:
        print(f"[config] {exc}", file=sys.stderr)
        return 1

    print(f"[ok] Circle client ready, env={client.config.env}")
    print(f"[ok] agent address={client.config.account_address}")

    try:
        total = client.get_total_usdc_balance()
        on_arc = client.get_usdc_token_balance()
        print(f"[balance] unified={total} micro-units, on_arc={on_arc} micro-units")
    except CircleClientError as exc:
        print(f"[balance] failed: {exc}")
        return 2

    # Quick Arc RPC liveness check
    rpc = ArcRPC(client.config.gateway_rpc_url)
    try:
        print(f"[arc] chain_id={hex(rpc.chain_id())} head={rpc.block_number()}")
    except Exception as exc:
        print(f"[arc] RPC failed: {exc}")
        return 3

    # Pricing — pretend a meme was listed 2h ago and got 12 quotes in the last hour
    quote_id = f"qt_{secrets.token_hex(4)}"
    meme_id = "mk_demo001"
    inp = PriceInputs(base_price=0.04, quotes_last_hour=12, hours_since_listed=2.0)
    price = effective_price(inp)
    print(f"[quote] meme={meme_id} quote_id={quote_id} effective_price={price:.6f} USDC")

    # Send a self-transfer of that amount across Gateway (demo only — same agent both sides)
    try:
        result = client.transfer_usdc(
            source_domain=ChainDomain.ARC_TESTNET,
            destination_domain=ChainDomain.ARC_TESTNET,
            amount=Decimal(str(price)),
            recipient=client.config.account_address,
            depositor=client.config.account_address,
            max_fee="0.02",          # cap fee so the nano payment stays nano
            wait_for_mint=True,
            destination_rpc_url=client.config.gateway_rpc_url,
        )
        print(f"[transfer] mint_tx={result.get('mint_tx_hash')}")
        print(f"[transfer] receipt status={result.get('receipt', {}).get('status')}")
    except CircleClientError as exc:
        print(f"[transfer] failed: {exc}")
        return 4

    print("[done] demo pipeline ran end-to-end")
    return 0


if __name__ == "__main__":
    sys.exit(main())