"""Smoke test: verify Memket skill imports + Arc RPC without needing a funded wallet."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, HERE)

from arc_rpc import ArcRPC
from pricing import PriceInputs, effective_price, spread_bps

RPC = "https://rpc.testnet.arc-node.thecanteenapp.com/v1/swrm_cd9380aeb34359fb50488103d2ffe9d45eea3d1a23a2fa242124c1fc4449464d"
r = ArcRPC(RPC)
print(f"arc chain_id   = {hex(r.chain_id())}")
print(f"arc head       = {r.block_number()}")
print(f"arc gas_price  = {r.gas_price()} wei")

inp = PriceInputs(base_price=0.04, quotes_last_hour=12, hours_since_listed=2.0)
print(f"demo price     = {effective_price(inp):.6f} USDC")
print(f"demo spread    = {spread_bps(2.0)} bps")

import circle_client
print(f"arc domain id  = {int(circle_client.ChainDomain.ARC_TESTNET)}")
print(f"arc USDC addr  = {circle_client.USDC_ADDRESSES[circle_client.ChainDomain.ARC_TESTNET]}")
print("smoke ok")