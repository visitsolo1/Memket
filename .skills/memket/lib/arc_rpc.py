"""Arc RPC client — minimal JSON-RPC over HTTPS.

Used by Memket to read state and submit USDC transfers on the Arc testnet.
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Any


class ArcRPC:
    """Tiny JSON-RPC client for Arc. No external deps."""

    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout
        self._id = 0

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": self._id,
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode())
        if "error" in body:
            raise ArcRPCError(body["error"])
        return body.get("result")

    # Convenience wrappers --------------------------------------------------

    def chain_id(self) -> int:
        return int(self.call("eth_chainId"), 16)

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber"), 16)

    def gas_price(self) -> int:
        return int(self.call("eth_gasPrice"), 16)

    def get_balance(self, address: str, block: str = "latest") -> int:
        return int(self.call("eth_getBalance", [address, block]), 16)


class ArcRPCError(RuntimeError):
    pass


# Smoke test
if __name__ == "__main__":
    RPC = "https://rpc.testnet.arc-node.thecanteenapp.com/v1/swrm_cd9380aeb34359fb50488103d2ffe9d45eea3d1a23a2fa242124c1fc4449464d"
    r = ArcRPC(RPC)
    print(f"chain_id   = {hex(r.chain_id())}")
    print(f"block_num  = {r.block_number()}")
    print(f"gas_price  = {r.gas_price()} wei")