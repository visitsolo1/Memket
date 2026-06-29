"""SQLite-backed store for Memket listings, quotes, and receipts."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS memes (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    title TEXT NOT NULL,
    image_url TEXT,
    base_price_usdc TEXT NOT NULL,
    listed_at INTEGER NOT NULL,
    for_sale INTEGER NOT NULL DEFAULT 1,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS quote_log (
    quote_id TEXT PRIMARY KEY,
    meme_id TEXT NOT NULL,
    buyer TEXT,
    price_usdc TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    receipt_id TEXT PRIMARY KEY,
    meme_id TEXT NOT NULL,
    prev_owner TEXT NOT NULL,
    new_owner TEXT NOT NULL,
    price_usdc TEXT NOT NULL,
    fee_usdc TEXT NOT NULL,
    arc_tx TEXT,
    settled_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    endpoint TEXT,
    ops TEXT,
    registered_at INTEGER NOT NULL
);
"""


@dataclass
class Meme:
    id: str
    owner: str
    title: str
    image_url: str | None
    base_price_usdc: str
    listed_at: int
    for_sale: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=5000")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ----- memes ----------------------------------------------------------

    def put_meme(self, m: Meme) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO memes (id, owner, title, image_url, base_price_usdc, listed_at, for_sale, metadata) VALUES (?,?,?,?,?,?,?,?)",
                (m.id, m.owner, m.title, m.image_url, m.base_price_usdc,
                 m.listed_at, int(m.for_sale), json.dumps(m.metadata)),
            )

    def get_meme(self, meme_id: str) -> Meme | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM memes WHERE id=?", (meme_id,)).fetchone()
        if not row:
            return None
        return self._row_to_meme(row)

    def list_memes(self, owner: str | None = None, for_sale_only: bool = False, limit: int = 100) -> list[Meme]:
        q = "SELECT * FROM memes"
        args: list[Any] = []
        wheres: list[str] = []
        if owner:
            wheres.append("owner=?")
            args.append(owner)
        if for_sale_only:
            wheres.append("for_sale=1")
        if wheres:
            q += " WHERE " + " AND ".join(wheres)
        q += " ORDER BY listed_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [self._row_to_meme(r) for r in rows]

    def mark_sold(self, meme_id: str, new_owner: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE memes SET for_sale=0, owner=? WHERE id=?", (new_owner, meme_id))

    @staticmethod
    def _row_to_meme(row: sqlite3.Row) -> Meme:
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return Meme(
            id=row["id"],
            owner=row["owner"],
            title=row["title"],
            image_url=row["image_url"],
            base_price_usdc=row["base_price_usdc"],
            listed_at=row["listed_at"],
            for_sale=bool(row["for_sale"]),
            metadata=meta,
        )

    # ----- quotes ---------------------------------------------------------

    def log_quote(self, quote_id: str, meme_id: str, buyer: str | None,
                  price_usdc: str, ttl_seconds: int = 60,
                  source: str = "self") -> int:
        now = int(time.time())
        expires = now + ttl_seconds
        with self._conn() as c:
            c.execute(
                "INSERT INTO quote_log (quote_id, meme_id, buyer, price_usdc, created_at, expires_at, source) VALUES (?,?,?,?,?,?,?)",
                (quote_id, meme_id, buyer, price_usdc, now, expires, source),
            )
        return expires

    def count_recent_quotes(self, meme_id: str, within_seconds: int = 3600) -> int:
        cutoff = int(time.time()) - within_seconds
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) as n FROM quote_log WHERE meme_id=? AND created_at>=?",
                (meme_id, cutoff),
            ).fetchone()
        return int(row["n"]) if row else 0

    # ----- receipts -------------------------------------------------------

    def put_receipt(self, receipt_id: str, meme_id: str, prev_owner: str,
                    new_owner: str, price_usdc: str, fee_usdc: str,
                    arc_tx: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO receipts (receipt_id, meme_id, prev_owner, new_owner, price_usdc, fee_usdc, arc_tx, settled_at) VALUES (?,?,?,?,?,?,?,?)",
                (receipt_id, meme_id, prev_owner, new_owner, price_usdc, fee_usdc, arc_tx, int(time.time())),
            )

    # ----- agents ---------------------------------------------------------

    def register_agent(self, name: str, wallet_address: str,
                       endpoint: str | None, ops: list[str] | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO agents (name, wallet_address, endpoint, ops, registered_at) VALUES (?,?,?,?,?)",
                (name, wallet_address, endpoint, json.dumps(ops or []), int(time.time())),
            )

    def get_agent(self, name: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["ops"] = json.loads(d["ops"]) if d["ops"] else []
        return d

    def list_agents(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM agents LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["ops"] = json.loads(d["ops"]) if d["ops"] else []
            out.append(d)
        return out
