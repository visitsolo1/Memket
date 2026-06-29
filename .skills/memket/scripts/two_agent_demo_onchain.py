"""On-chain version of the two-agent demo.

Same as two_agent_demo.py, but step 6 performs a real Arc USDC nanopayment
via Circle Gateway if EVM_PRIVATE_KEY + GATEWAY_RPC_URL are set.

Use this when you have a funded wallet (testnet USDC deposited into Gateway).
Run after two_agent_demo.py — same Arc testnet.
"""
from __future__ import annotations

import os
import sys
import time
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

from two_agent_demo import run, C, G, Y, R, B, N, banner, step, info, spawn_agent  # noqa: E402


def main() -> int:
    if not os.getenv("EVM_PRIVATE_KEY") or not os.getenv("GATEWAY_RPC_URL"):
        print(f"{R}On-chain demo requires EVM_PRIVATE_KEY and GATEWAY_RPC_URL env vars.{N}")
        print(f"{Y}Falling back to simulated settlement version.{N}")
        return run(spawn=True)

    from circle_client import ChainDomain, CircleClient, CircleClientError

    try:
        client = CircleClient.from_env()
    except CircleClientError as exc:
        print(f"{R}Could not init Circle client: {exc}{N}")
        return 1

    total = client.get_total_usdc_balance()
    print(f"{G}[ok] unified USDC balance: {total} micro-units{N}")
    if total < 100_000:
        print(f"{R}Balance too low. Run client.deposit_usdc(...) first.{N}")
        return 2

    # Run the off-chain demo first to set up listings + virality...
    demo_dir = "/tmp/memket_onchain"
    os.makedirs(demo_dir, exist_ok=True)
    for f in (f"{demo_dir}/alice.db", f"{demo_dir}/bob.db"):
        try: os.remove(f)
        except FileNotFoundError: pass
    alice_proc = spawn_agent("alice", 8001, f"{demo_dir}/alice.db")
    bob_proc = spawn_agent("bob", 8002, f"{demo_dir}/bob.db")
    try:
        from client import MemketClient
        from store import Meme
        alice_client = MemketClient("http://127.0.0.1:8001", name="alice")
        bob_client = MemketClient("http://127.0.0.1:8001", name="bob")

        banner("Memket — On-chain variant")
        step(1, "Alice lists a meme")
        listed = alice_client.list_meme("doge-to-the-moon", "0.05")
        meme_id = listed["data"]["meme_id"]
        info(f"listed: {meme_id}")

        step(2, "Bob pumps virality with 8 quotes")
        for _ in range(8):
            q = bob_client.quote(meme_id, buyer="bob")
        info(f"effective price: {Y}{B}{q['data']['effective_price_usdc']} USDC{N}")

        step(3, "Bob pays via Circle Gateway — real USDC transfer on Arc")
        try:
            res = client.transfer_usdc(
                source_domain=ChainDomain.ARC_TESTNET,
                destination_domain=ChainDomain.ARC_TESTNET,
                amount=Decimal(q["data"]["effective_price_usdc"]),
                recipient=alice_client.health(),  # not used; ignore
                depositor=client.config.account_address,
                max_fee="0.02",
                wait_for_mint=True,
                destination_rpc_url=client.config.gateway_rpc_url,
            )
            mint_tx = res.get("mint_tx_hash")
            info(f"{G}✓ mint_tx={mint_tx}{N}")
        except CircleClientError as exc:
            print(f"{R}transfer failed: {exc}{N}")
            return 3

        step(4, "Bob posts the buy with the on-chain tx hash")
        receipt = bob_client.buy(meme_id, buyer="bob", quote_id=q["data"]["quote_id"], tx_hash=mint_tx)
        info(f"receipt: {receipt['data']}")
        info(f"{G}✓ meme ownership recorded against the on-chain Arc tx{N}")

        banner("On-chain demo complete")
        return 0
    finally:
        for p in (alice_proc, bob_proc):
            if p is not None:
                p.terminate()
                try: p.wait(timeout=3)
                except Exception: p.kill()


if __name__ == "__main__":
    sys.exit(main())
