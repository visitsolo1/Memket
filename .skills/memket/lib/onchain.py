"""On-chain settlement for Memket: direct ERC20 USDC transfer on Arc.

For the demo, we use the raw USDC.transfer() call (not Circle Gateway's
unified balance). This keeps the demo simple, requires only that the
buyer wallet holds USDC on Arc, and produces a real, verifiable tx hash
that judges can look up on the Arc testnet explorer.

For a production deployment, switch to CircleClient.transfer_usdc() which
also handles cross-chain unified balance — see scripts/two_agent_demo_onchain.py.
"""
from __future__ import annotations

import os
import time
from typing import Any

from web3 import Web3
from eth_account import Account


USDC_ARC_TESTNET = "0x3600000000000000000000000000000000000000"

ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
]


def _w3(rpc_url: str) -> Web3:
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))


def transfer_usdc_on_arc(
    *,
    rpc_url: str,
    private_key: str,
    to_address: str,
    amount_micro: int,
    memo_text: str | None = None,
    wait_timeout: int = 120,
) -> dict[str, Any]:
    """Send a raw ERC20 USDC transfer on Arc and wait for the receipt.

    amount_micro is in 6-decimal USDC micro-units (so 0.05 USDC = 50_000).

    Returns the dict:
        {
          "tx_hash": "0x...",
          "from":   "0x...",
          "to":     "0x...",
          "amount_micro": 50000,
          "block":  49631756,
          "status": 1,
          "gas_used": 42682,
          "memo":   "mk:<id>:qt:<quote_id>" (or None),
          "settled_at": 1782822933,
        }
    """
    w3 = _w3(rpc_url)
    acct = Account.from_key(private_key if private_key.startswith("0x") else "0x" + private_key)
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ARC_TESTNET), abi=ERC20_ABI)

    nonce = w3.eth.get_transaction_count(acct.address)
    tx = usdc.functions.transfer(Web3.to_checksum_address(to_address), int(amount_micro)).build_transaction({
        "from": acct.address,
        "nonce": nonce,
        "gas": 200_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": w3.eth.chain_id,
    })

    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=wait_timeout)

    return {
        "tx_hash": tx_hash.hex(),
        "from": acct.address,
        "to": Web3.to_checksum_address(to_address),
        "amount_micro": int(amount_micro),
        "block": int(rcpt.blockNumber),
        "status": int(rcpt.status),
        "gas_used": int(rcpt.gasUsed),
        "memo": memo_text,
        "settled_at": int(time.time()),
        "chain_id": w3.eth.chain_id,
    }


def usdc_balance_on_arc(rpc_url: str, address: str) -> int:
    """Return the on-chain USDC balance (micro-units) for `address` on Arc testnet."""
    w3 = _w3(rpc_url)
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ARC_TESTNET), abi=ERC20_ABI)
    return int(usdc.functions.balanceOf(Web3.to_checksum_address(address)).call())
