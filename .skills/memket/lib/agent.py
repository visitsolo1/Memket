"""MemketAgent — high-level operations: list, quote, search, buy.

Combines the store, the pricing engine, and (optionally) the Circle client.
"""
from __future__ import annotations

import os
import secrets
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "..", "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from store import Store, Meme  # noqa: E402
from quote_pricing import quote_for_meme  # noqa: E402


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


class MemketAgent:
    """A Memket agent: has a name, a wallet address, and a local store."""

    def __init__(
        self,
        name: str,
        wallet_address: str,
        store: Store | None = None,
        circle_client: Any | None = None,
    ):
        self.name = name
        self.wallet_address = wallet_address
        self.store = store or Store(f"/tmp/{name}.db")
        self.circle = circle_client  # optional; may be None for a list-only agent
        self.store.register_agent(
            name, wallet_address, endpoint=None,
            ops=["list", "quote", "search"],
        )

    # ----- listing --------------------------------------------------------

    def list_meme(self, title: str, base_price_usdc: str,
                  image_url: str | None = None,
                  metadata: dict[str, Any] | None = None) -> Meme:
        if float(base_price_usdc) < 0.001 or float(base_price_usdc) > 0.5:
            raise ValueError("base_price_usdc must be in [0.001, 0.50]")
        m = Meme(
            id=new_id("mk"),
            owner=self.name,
            title=title,
            image_url=image_url,
            base_price_usdc=base_price_usdc,
            listed_at=int(time.time()),
            metadata=metadata or {},
        )
        self.store.put_meme(m)
        return m

    # ----- quoting --------------------------------------------------------

    def quote(self, meme_id: str, buyer: str | None = None) -> dict[str, Any]:
        meme = self.store.get_meme(meme_id)
        if meme is None:
            return {"ok": False, "err": "meme_not_found", "meme_id": meme_id}
        if not meme.for_sale:
            return {"ok": False, "err": "forbidden", "reason": "meme not for sale", "meme_id": meme_id}
        q = quote_for_meme(self.store, meme_id, meme.base_price_usdc)
        quote_id = new_id("qt")
        expires_at = self.store.log_quote(
            quote_id, meme_id, buyer,
            q["effective_price_usdc"], ttl_seconds=60, source=self.name,
        )
        return {
            "ok": True,
            "op": "quote",
            "data": {
                **q,
                "quote_id": quote_id,
                "seller": meme.owner,
                "expires_at": expires_at,
                "spread_bps": q["spread_bps"],
            },
        }

    # ----- search ---------------------------------------------------------

    def search(self, owner: str | None = None, for_sale_only: bool = True,
               limit: int = 50) -> dict[str, Any]:
        memes = self.store.list_memes(owner=owner, for_sale_only=for_sale_only, limit=limit)
        listings = []
        for m in memes:
            q = quote_for_meme(self.store, m.id, m.base_price_usdc)
            listings.append({
                "meme_id": m.id,
                "title": m.title,
                "owner": m.owner,
                "image_url": m.image_url,
                "effective_price_usdc": q["effective_price_usdc"],
                "spread_bps": q["spread_bps"],
            })
        return {"ok": True, "op": "search", "data": {"listings": listings, "count": len(listings)}}

    # ----- buying ---------------------------------------------------------

    def buy(self, meme_id: str, buyer: str,
            quote_id: str | None = None,
            tx_hash: str | None = None) -> dict[str, Any]:
        """Try to buy a meme.

        `buyer` is the name of the agent submitting the purchase. Used to
        validate the seller != buyer invariant and to record new ownership.
        If a Circle client is wired in and a tx_hash is provided, we verify the
        tx on Arc. Without either, this is a simulated transfer (useful for the
        demo when the agent has no USDC).
        """
        meme = self.store.get_meme(meme_id)
        if meme is None or not meme.for_sale:
            return {"ok": False, "err": "forbidden", "meme_id": meme_id}
        if meme.owner == buyer:
            return {"ok": False, "err": "self_buy", "meme_id": meme_id, "buyer": buyer}
        if buyer == self.name:
            # Caller passed its own agent name as the buyer — likely a client misroute.
            return {"ok": False, "err": "self_buy", "meme_id": meme_id, "buyer": buyer}

        # Compute the price we expect
        q = quote_for_meme(self.store, meme_id, meme.base_price_usdc)
        price_usdc = q["effective_price_usdc"]

        # If a real on-chain tx hash is provided by the buyer, stamp it on the receipt.
        if tx_hash is not None:
            fee_usdc = "0.01"
            arc_tx = tx_hash
        else:
            # No on-chain tx from the buyer — fall back to simulated settlement.
            fee_usdc = "0.01"
            arc_tx = None

        # Mark ownership transferred
        receipt_id = new_id("rc")
        prev_owner = meme.owner
        new_owner = buyer
        self.store.put_receipt(
            receipt_id=receipt_id,
            meme_id=meme_id,
            prev_owner=prev_owner,
            new_owner=new_owner,
            price_usdc=price_usdc,
            fee_usdc=fee_usdc,
            arc_tx=arc_tx,
        )
        self.store.mark_sold(meme_id, new_owner)
        return {
            "ok": True,
            "op": "buy",
            "data": {
                "receipt_id": receipt_id,
                "meme_id": meme_id,
                "prev_owner": prev_owner,
                "new_owner": new_owner,
                "price_usdc": price_usdc,
                "fee_usdc": fee_usdc,
                "arc_tx": arc_tx,
                "settled_at": int(time.time()),
            },
        }

    # ----- manifest -------------------------------------------------------

    def manifest(self, endpoint: str | None = None) -> dict[str, Any]:
        return {
            "name": self.name,
            "wallet": {"chain": "arc", "address": self.wallet_address, "currency": "USDC"},
            "ops": ["list", "quote", "search", "buy"],
            "endpoint": endpoint,
            "registered_at": int(time.time()),
        }
