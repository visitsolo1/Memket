"""Memket FastAPI server — exposes the agent's ops over HTTP.

Run:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from agent import MemketAgent  # noqa: E402


# Module-level so FastAPI's reflection can resolve the type at decoration time.
class ListReq(BaseModel):
    title: str
    base_price_usdc: str
    image_url: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class BuyReq(BaseModel):
    quote_id: Optional[str] = None
    tx_hash: Optional[str] = None
    buyer: Optional[str] = None


def make_app(agent: MemketAgent, external_endpoint: str | None = None) -> FastAPI:
    app = FastAPI(title=f"Memket/{agent.name}")

    @app.get("/.well-known/memket.json")
    def manifest():
        return agent.manifest(endpoint=external_endpoint)

    @app.get("/health")
    def health():
        return {"ok": True, "agent": agent.name, "wallet": agent.wallet_address}

    @app.get("/memes")
    def list_memes(owner: str | None = None, for_sale_only: bool = True, limit: int = 50):
        import sys
        ms = agent.store.list_memes(owner=owner, for_sale_only=for_sale_only, limit=limit)
        all_memes = agent.store.list_memes(limit=1000)
        print(f"   SRV DEBUG list_memes owner={owner} for_sale_only={for_sale_only} path={agent.store.path} -> {len(ms)} hits / total={len(all_memes)} ids={[m.id for m in all_memes]}", file=sys.stderr, flush=True)
        return agent.search(owner=owner, for_sale_only=for_sale_only, limit=limit)

    @app.post("/memes")
    def create_meme(req: ListReq):
        import sys
        print(f"   SRV DEBUG create_meme: store.path={agent.store.path}", file=sys.stderr, flush=True)
        try:
            m = agent.list_meme(req.title, req.base_price_usdc, req.image_url, req.metadata or {})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        print(f"   SRV DEBUG put_meme id={m.id}", file=sys.stderr, flush=True)
        return {"ok": True, "data": {"meme_id": m.id, "title": m.title, "owner": m.owner, "base_price_usdc": m.base_price_usdc}}

    @app.get("/memes/{meme_id}/quote")
    def quote(meme_id: str, buyer: str | None = None):
        res = agent.quote(meme_id, buyer=buyer)
        if not res["ok"]:
            raise HTTPException(status_code=404, detail=res)
        return res

    @app.post("/memes/{meme_id}/buy")
    def buy(meme_id: str, req: BuyReq, buyer: str | None = None):
        buyer_name = req.buyer or buyer or agent.name
        print(f"   SRV DEBUG buy meme={meme_id} req.buyer={req.buyer!r} query_buyer={buyer!r} -> buyer_name={buyer_name!r}", file=sys.stderr, flush=True)
        res = agent.buy(meme_id, buyer=buyer_name, quote_id=req.quote_id, tx_hash=req.tx_hash)
        if not res["ok"]:
            raise HTTPException(status_code=400, detail=res)
        return res

    return app


# Default app for `uvicorn server:app` when env vars are present.
_NAME = os.getenv("MEMKET_AGENT_NAME", "agent")
_ADDR = os.getenv("MEMKET_AGENT_ADDRESS", "0x0000000000000000000000000000000000000000")
_DB = os.getenv("MEMKET_STORE_PATH", f"/tmp/{_NAME}.db")
from store import Store
_default_store = Store(_DB)
app = make_app(MemketAgent(name=_NAME, wallet_address=_ADDR, store=_default_store),
               external_endpoint=os.getenv("MEMKET_PUBLIC_URL"))
