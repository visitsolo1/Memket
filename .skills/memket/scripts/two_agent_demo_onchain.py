"""Memket two-agent demo with REAL on-chain USDC settlement on Arc.

Spawns two FastAPI Memket agents (Alice and Bob) and a buyer-side wallet.
Bob pays Alice directly via ERC20 transfer on Arc testnet — every demo run
emits a real, verifiable tx hash that judges can paste into the Arc explorer.

Required env:
    EVM_PRIVATE_KEY        : funded testnet wallet for Bob (the buyer)
    GATEWAY_RPC_URL        : Arc RPC URL (Bob signs and reads receipt from here)
    MEMKET_BUYER_NAME      : (optional, default "bob") — name attached to receipts
    MEMKET_SELLER_NAME     : (optional, default "alice") — seller's manifest name
    MEMKET_SELLER_ADDRESS  : (optional, default 0xSELLER) — Arc addr to receive USDC

Usage:
    EVM_PRIVATE_KEY="0x..." \
    GATEWAY_RPC_URL="https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>" \
    python3 two_agent_demo_onchain.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

from two_agent_demo import (  # noqa: E402
    C, G, Y, R, B, N, banner, step, info, spawn_agent,
)
from client import MemketClient  # noqa: E402
from onchain import (  # noqa: E402
    USDC_ARC_TESTNET,
    transfer_usdc_on_arc,
    usdc_balance_on_arc,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alice-port", type=int, default=8001)
    ap.add_argument("--bob-port", type=int, default=8002)
    ap.add_argument("--no-spawn", action="store_true")
    args = ap.parse_args()

    pk = os.getenv("EVM_PRIVATE_KEY", "").strip()
    if not pk:
        print(f"{R}EVM_PRIVATE_KEY env var is required for real settlement.{N}")
        return 1
    rpc_url = os.getenv("GATEWAY_RPC_URL", "").strip()
    if not rpc_url:
        print(f"{R}GATEWAY_RPC_URL env var is required.{N}")
        return 1

    seller_name = os.getenv("MEMKET_SELLER_NAME", "alice")
    buyer_name = os.getenv("MEMKET_BUYER_NAME", "bob")
    seller_address = os.getenv("MEMKET_SELLER_ADDRESS", "0x" + "S" * 40)

    demo_dir = "/tmp/memket_onchain"
    os.makedirs(demo_dir, exist_ok=True)
    for f in (f"{demo_dir}/{seller_name}.db", f"{demo_dir}/{buyer_name}.db"):
        try: os.remove(f)
        except FileNotFoundError: pass

    seller_proc = spawn_agent(seller_name, args.alice_port,
                              f"{demo_dir}/{seller_name}.db",
                              log_dir=demo_dir)
    buyer_proc = spawn_agent(buyer_name, args.bob_port,
                             f"{demo_dir}/{buyer_name}.db",
                             log_dir=demo_dir)

    try:
        banner(f"Memket — Two-Agent Demo with REAL Arc USDC Settlement")

        step(1, f"{seller_name} publishes manifest, seller.wallet = {seller_address}")
        seller_client = MemketClient(f"http://127.0.0.1:{args.alice_port}", name=seller_name)
        m = seller_client.manifest()
        info(f"name={m['name']} ops={m['ops']}")

        step(2, f"{buyer_name} discovers {seller_name} and pre-checks USDC balance on Arc")
        buyer_client = MemketClient(f"http://127.0.0.1:{args.alice_port}", name=buyer_name)
        bal = usdc_balance_on_arc(rpc_url, _addr_from_pk(pk))
        info(f"{buyer_name}'s Arc USDC balance: {bal} micro-units ({bal/1_000_000:.6f} USDC)")
        if bal < 1_000_000:
            print(f"{R}buyer has less than 1 USDC — fund the wallet first.{N}")
            return 2

        step(3, f"{seller_name} lists the meme")
        listed = seller_client.list_meme("doge-to-the-moon", "0.05",
                                         image_url="https://example.com/doge.jpg",
                                         metadata={"tags": ["doge", "moon"]})
        meme_id = listed["data"]["meme_id"]
        info(f"{G}✓ listed{N}: {meme_id} @ 0.05 USDC base")

        step(4, f"{buyer_name} searches {seller_name}'s inventory")
        results = buyer_client.search(owner=seller_name)
        info(f"{buyer_name} sees {results['data']['count']} listing(s) on {seller_name}:")
        for L in results["data"]["listings"]:
            info(f"  • {L['meme_id']}  '{L['title']}'  "
                 f"{Y}{L['effective_price_usdc']} USDC{N}  spread={L['spread_bps']}bps")

        step(5, f"{buyer_name} gets a quote, pumps virality (live pricing)")
        for _ in range(8):
            q = buyer_client.quote(meme_id, buyer=buyer_name)
        info(f"{Y}virality built{N}: 8 quote calls in the last minute from {buyer_name}")
        info(f"  base   : {q['data']['base_price_usdc']} USDC")
        info(f"  price  : {Y}{B}{q['data']['effective_price_usdc']} USDC{N}")
        info(f"  quote  : {q['data']['quote_id']} (ttl 60s)")

        step(6, f"{buyer_name} pays {seller_name} — REAL ERC20 USDC transfer on Arc")
        # Construct a memo like mk:<id>:qt:<quote_id> for receipts / explorers
        memo = f"mk:{meme_id.removeprefix('mk_')}:qt:{q['data']['quote_id'].removeprefix('qt_')}"
        amount_micro = int(round(float(q['data']['effective_price_usdc']) * 1_000_000))
        try:
            payment = transfer_usdc_on_arc(
                rpc_url=rpc_url,
                private_key=pk,
                to_address=seller_address,
                amount_micro=amount_micro,
                memo_text=memo,
            )
        except Exception as exc:
            print(f"{R}on-chain transfer failed: {exc}{N}")
            return 3

        info(f"{G}✓ on-chain payment confirmed{N}")
        info(f"  tx_hash : {B}{payment['tx_hash']}{N}")
        info(f"  block   : {payment['block']}  status={payment['status']}  gas={payment['gas_used']}")
        info(f"  amount  : {payment['amount_micro']} micro-USDC "
             f"({payment['amount_micro']/1_000_000:.6f} USDC)")
        info(f"  from→to : {payment['from']} → {payment['to']}")
        info(f"  explorer: {Y}https://testnet.arcscan.org/tx/{payment['tx_hash']}{N}")

        step(7, f"{buyer_name} posts the buy with the on-chain tx hash")
        receipt = buyer_client.buy(
            meme_id,
            buyer=buyer_name,
            quote_id=q['data']['quote_id'],
            tx_hash=payment['tx_hash'],
        )
        if not receipt.get("ok"):
            print(f"{R}buy failed: {receipt}{N}")
            return 4
        info(f"{G}✓ receipt emitted with on-chain provenance{N}")
        for k, v in receipt['data'].items():
            info(f"  {k}: {v}")

        step(8, f"{seller_name} reflects the new ownership")
        seller_view = seller_client.search(owner=seller_name, for_sale_only=True)
        info(f"{seller_name} has {seller_view['data']['count']} active listing(s) (meme just sold)")
        buyer_view = seller_client.search(owner=buyer_name, for_sale_only=False)
        info(f"{seller_name} sees {buyer_view['data']['count']} meme(s) now owned by {buyer_name}:")
        for L in buyer_view["data"]["listings"]:
            info(f"  • {L['meme_id']} '{L['title']}' owner={L['owner']}")

        step(9, f"{buyer_name} confirms the new state")
        bal_after = usdc_balance_on_arc(rpc_url, _addr_from_pk(pk))
        info(f"{buyer_name}'s Arc USDC balance: {bal_after} micro-units "
             f"({bal_after/1_000_000:.6f} USDC)  [was {bal} before the trade]")

        banner("Demo complete — REAL on-chain Arc USDC settlement")
        print(f"{G}Verified on-chain at:{N}")
        print(f"  https://testnet.arcscan.org/tx/{payment['tx_hash']}")
        print(f"{G}Two AI agents discovered each other, negotiated a price, and "
              f"exchanged a real USDC nanopayment on Arc testnet.{N}\n")
        return 0
    finally:
        for p in (seller_proc, buyer_proc):
            if p is not None:
                p.terminate()
                try: p.wait(timeout=3)
                except Exception: p.kill()


def _addr_from_pk(pk: str) -> str:
    from eth_account import Account
    return Account.from_key(pk if pk.startswith("0x") else "0x" + pk).address


if __name__ == "__main__":
    sys.exit(main())
