"""MemketClient — HTTP client that talks to remote Memket agents."""
from __future__ import annotations

import os
import sys
from typing import Any

import urllib.request
import urllib.parse
import json

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


class MemketClient:
    """HTTP client for a remote Memket agent endpoint."""

    def __init__(self, base_url: str, name: str | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.name = name or base_url
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None,
                 query: dict | None = None) -> dict[str, Any]:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"ok": False, "err": "http_error", "status": e.code, "body": e.read().decode()[:300]}
        except Exception as e:
            return {"ok": False, "err": "transport_error", "message": str(e)}

    # ----- ops ------------------------------------------------------------

    def manifest(self) -> dict[str, Any]:
        return self._request("GET", "/.well-known/memket.json")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def search(self, owner: str | None = None, for_sale_only: bool = True,
               limit: int = 50) -> dict[str, Any]:
        q: dict[str, Any] = {"for_sale_only": str(for_sale_only).lower(), "limit": str(limit)}
        if owner:
            q["owner"] = owner
        return self._request("GET", "/memes", query=q)

    def quote(self, meme_id: str, buyer: str | None = None) -> dict[str, Any]:
        q = {"buyer": buyer} if buyer else None
        return self._request("GET", f"/memes/{meme_id}/quote", query=q)

    def buy(self, meme_id: str, buyer: str | None = None,
            quote_id: str | None = None,
            tx_hash: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if buyer:
            body["buyer"] = buyer
        if quote_id:
            body["quote_id"] = quote_id
        if tx_hash:
            body["tx_hash"] = tx_hash
        return self._request("POST", f"/memes/{meme_id}/buy", body=body)

    def list_meme(self, title: str, base_price_usdc: str,
                  image_url: str | None = None,
                  metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "base_price_usdc": base_price_usdc}
        if image_url:
            body["image_url"] = image_url
        if metadata:
            body["metadata"] = metadata
        return self._request("POST", "/memes", body=body)


def discover(base_url: str) -> dict[str, Any]:
    """Fetch a peer's manifest — used for cross-agent search indexing."""
    return MemketClient(base_url).manifest()
