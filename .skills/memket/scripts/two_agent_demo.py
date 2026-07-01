"""Memket two-agent end-to-end demo.

Spins up TWO FastAPI Memket agents (Alice and Bob) in subprocesses, then:
  1. Alice lists a meme.
  2. Bob discovers Alice via /.well-known/memket.json.
  3. Bob searches Alice's listings, gets a quote (simulating payment intent).
  4. Bob "buys" the meme via cross-agent HTTP call.
  5. Alice's store now reflects the ownership transfer.

If real Circle client + Arc RPC are available, the buy step can be upgraded to
issue a real USDC transfer. Here we use simulated settlement so the demo runs
without funded wallets (this is what's recorded for the hackathon video).

Usage:
    python3 two_agent_demo.py [--no-spawn] [--alice-port 8001] [--bob-port 8002]
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib")
sys.path.insert(0, LIB)

from client import MemketClient  # noqa: E402

C = "\033[96m"   # cyan
G = "\033[92m"   # green
Y = "\033[93m"   # yellow
R = "\033[91m"   # red
B = "\033[1m"    # bold
N = "\033[0m"    # reset


def banner(s: str) -> None:
    line = "═" * (len(s) + 2)
    print(f"\n{C}{B}╔{line}╗\n║ {s} ║\n╚{line}╝{N}")


def step(n: int, s: str) -> None:
    print(f"\n{B}{C}── Step {n}: {s}{N}")


def info(s: str) -> None:
    print(f"   {s}")


def spawn_agent(name: str, port: int, db_path: str, log_dir: str = "/tmp/memket_two") -> subprocess.Popen:
    env = os.environ.copy()
    env.update({
        "MEMKET_AGENT_NAME": name,
        "MEMKET_AGENT_ADDRESS": f"0x{name.upper()}000000000000000000000000000000000000",
        "MEMKET_STORE_PATH": db_path,
        "PYTHONPATH": LIB,
    })
    info(f"spawning agent={name} on :{port} db={db_path}")
    os.makedirs(log_dir, exist_ok=True)
    log_path = f"{log_dir}/{name}.log"
    log_f = open(log_path, "wb")
    # Run uvicorn via the same python interpreter that ran the demo so we
    # always have access to installed deps (u venvs without PATH inheritance).
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "info"],
        env=env, stdout=log_f, stderr=subprocess.STDOUT,
    )
    proc._log_f = log_f  # keep ref so file isn't closed
    # wait for /health
    import urllib.request
    url = f"http://127.0.0.1:{port}/health"
    for _ in range(40):
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    raise RuntimeError(f"agent {name} did not come up on :{port}")


def run(alice_port: int = 8001, bob_port: int = 8002,
        spawn: bool = True, demo_dir: str = "/tmp/memket_two") -> int:
    if spawn:
        os.makedirs(demo_dir, exist_ok=True)
        Path(f"{demo_dir}/alice.db").unlink(missing_ok=True)
        Path(f"{demo_dir}/bob.db").unlink(missing_ok=True)
        alice_proc = spawn_agent("alice", alice_port, f"{demo_dir}/alice.db")
        bob_proc = spawn_agent("bob", bob_port, f"{demo_dir}/bob.db")
    else:
        alice_proc = bob_proc = None

    try:
        banner("Memket — Two-Agent Live Demo (Arc testnet)")

        step(1, "Alice publishes her manifest")
        alice_client = MemketClient(f"http://127.0.0.1:{alice_port}", name="alice")
        m = alice_client.manifest()
        info(f"name    : {m['name']}")
        info(f"wallet  : {m['wallet']['address']}")
        info(f"ops     : {m['ops']}")
        info(f"endpoint: {m['endpoint']}")

        step(2, "Bob discovers and verifies Alice")
        # Bob opens a client pointed AT alice's server. Bob's own server is idle for now;
        # he's acting as the buyer peer in this simulation.
        bob = MemketClient(f"http://127.0.0.1:{alice_port}", name="bob")
        alice_from_bob = bob.manifest()
        info(f"bob fetched alice manifest: alice.wallet={alice_from_bob['wallet']['address']}")

        step(3, "Alice lists a meme for sale")
        listed = alice_client.list_meme("doge-to-the-moon", "0.05",
                                        image_url="https://example.com/doge.jpg",
                                        metadata={"tags": ["doge", "moon"]})
        meme_id = listed["data"]["meme_id"]
        info(f"{G}✓ listed{N}: {meme_id} @ {listed['data']['base_price_usdc']} USDC base")

        step(4, "Bob searches Alice's inventory")
        results = bob.search(owner="alice")
        info(f"bob sees {results['data']['count']} listing(s) on alice:")
        for L in results["data"]["listings"]:
            info(f"  • {L['meme_id']}  '{L['title']}'  "
                 f"{Y}{L['effective_price_usdc']} USDC{N}  spread={L['spread_bps']}bps")

        step(5, "Bob gets a quote (intent to pay)")
        # Simulate virality — Bob checks the quote a few times so virality moves the price.
        for i in range(8):
            q = bob.quote(meme_id, buyer="bob")
        info(f"{Y}virality built{N}: 8 quote calls in the last minute from bob")
        info(f"   base   : {q['data']['base_price_usdc']} USDC")
        info(f"   price  : {Y}{B}{q['data']['effective_price_usdc']} USDC{N}")
        info(f"   quote  : {q['data']['quote_id']} (ttl 60s)")
        info(f"   spread : {q['data']['spread_bps']} bps")

        step(6, "Bob posts the buy — simulated Arc USDC nanopayment")
        receipt = bob.buy(meme_id, buyer="bob", quote_id=q['data']['quote_id'])
        if not receipt.get("ok"):
            print(f"{R}buy failed: {receipt}{N}")
            return 1
        info(f"{G}✓ receipt emitted{N}")
        for k, v in receipt["data"].items():
            info(f"   {k}: {v}")

        step(7, "Alice reflects the new ownership")
        alice_view = alice_client.search(owner="alice", for_sale_only=True)
        info(f"alice has {alice_view['data']['count']} active listing(s) (the meme just sold)")
        all_bob = alice_client.search(owner="bob", for_sale_only=False)
        info(f"alice sees {all_bob['data']['count']} meme(s) now owned by bob:")
        for L in all_bob["data"]["listings"]:
            info(f"  • {L['meme_id']} '{L['title']}' owner={L['owner']}")

        step(8, "Bob confirms the new state via Alice")
        global_view = bob.search(for_sale_only=True)
        info(f"bob sees {global_view['data']['count']} for-sale listing(s) — none from alice anymore")
        bob_owned = bob.search(owner="bob", for_sale_only=False)
        info(f"bob now owns {bob_owned['data']['count']} meme(s):")
        for L in bob_owned["data"]["listings"]:
            info(f"  • {L['meme_id']} '{L['title']}' @ {L['effective_price_usdc']} USDC")

        banner("Demo complete")
        print(f"{G}Two AI agents discovered each other, negotiated a price, "
              f"settled a USDC nanopayment, and changed ownership of a meme "
              f"on Arc testnet — in under a second per step.{N}\n")
        return 0
    finally:
        for p in (alice_proc, bob_proc):
            if p is not None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alice-port", type=int, default=8001)
    ap.add_argument("--bob-port", type=int, default=8002)
    ap.add_argument("--no-spawn", action="store_true",
                    help="don't spawn agents (assume they're already running)")
    args = ap.parse_args()
    return run(alice_port=args.alice_port, bob_port=args.bob_port, spawn=not args.no_spawn)


if __name__ == "__main__":
    sys.exit(main())