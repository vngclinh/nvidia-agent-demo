"""
Assignment 3 — MCP HTTP Client
Thin client connecting to the Invoice MCP server over HTTP (streamable-http transport).
"""

import asyncio
import concurrent.futures
import os
from typing import Any

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

MCP_PORT = int(os.environ.get("MCP_PORT", 8765))
MCP_URL = f"http://127.0.0.1:{MCP_PORT}/mcp/"


# ── Async core ────────────────────────────────────────────────────────────────

async def _list_tools_async(url: str) -> list[dict]:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [{"name": t.name, "description": t.description} for t in result.tools]


async def _call_tool_async(url: str, tool_name: str, arguments: dict[str, Any]) -> str:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return "\n".join(texts)


def _run_in_new_loop(coro):
    """Chạy coroutine trong thread riêng — tránh conflict với event loop của LangGraph."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


# ── Sync wrapper ──────────────────────────────────────────────────────────────

class InvoiceMCPClient:
    """Sync wrapper quanh MCP SDK async client — dùng từ LangGraph nodes."""

    def __init__(self, url: str = MCP_URL):
        self.url = url

    def list_tools(self) -> list[dict]:
        return _run_in_new_loop(_list_tools_async(self.url))

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        return _run_in_new_loop(_call_tool_async(self.url, tool_name, arguments))

    def invoice_search(self, customer_query: str, artist_or_track: str = "") -> str:
        args: dict[str, Any] = {"customer_query": customer_query}
        if artist_or_track:
            args["artist_or_track"] = artist_or_track
        return self.call_tool("invoice_search", args)

    def invoice_refund(self, invoice_id: int) -> str:
        return self.call_tool("invoice_refund", {"invoice_id": invoice_id})
