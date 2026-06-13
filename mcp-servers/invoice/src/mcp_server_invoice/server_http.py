"""
Assignment 1 — Invoice MCP Server
Low-level MCP SDK pattern (Module 03):
  Server('invoice') + @list_tools + @call_tool + Starlette/Uvicorn

Chạy:
    python server_http.py

Endpoint: http://0.0.0.0:8765/mcp
"""

import contextlib
import os
import sqlite3
from pathlib import Path
from typing import Any

import mcp.types as types
import uvicorn
from dotenv import find_dotenv, load_dotenv
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

# ── Load .env (tự tìm ở thư mục gốc dự án) ──────────────────────────────────────
load_dotenv(find_dotenv())

# ── Config ─────────────────────────────────────────────────────────────────────
MCP_PORT = int(os.environ.get("MCP_PORT", 8765))
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chinook.db"


# ── Database helpers ───────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── MCP Server (low-level SDK — Module 03 pattern) ────────────────────────────

server = Server("invoice")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="invoice_search",
            description=(
                "Search invoices by customer name or phone number, "
                "optionally filtered by artist or track name. "
                "Returns invoice lines with track, album, and artist details."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_query": {
                        "type": "string",
                        "description": "Customer first name, last name, or phone number (partial match supported)",
                    },
                    "artist_or_track": {
                        "type": "string",
                        "description": "Optional: filter by artist name or track name (partial match)",
                    },
                },
                "required": ["customer_query"],
            },
        ),
        types.Tool(
            name="invoice_refund",
            description=(
                "Process a refund for a specific invoice. "
                "Deletes all invoice lines and sets the invoice total to 0. "
                "Returns the refunded amount or an error message."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "integer",
                        "description": "The InvoiceId to refund",
                    },
                },
                "required": ["invoice_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    if arguments is None:
        arguments = {}

    if name == "invoice_search":
        return _invoice_search(arguments)
    elif name == "invoice_refund":
        return _invoice_refund(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


# ── Tool implementations ───────────────────────────────────────────────────────

def _invoice_search(args: dict) -> list[types.TextContent]:
    customer_query = args.get("customer_query", "")
    artist_or_track = args.get("artist_or_track", "")
    pattern = f"%{customer_query}%"

    sql = """
        SELECT
            i.InvoiceId,
            i.InvoiceDate,
            i.Total,
            c.FirstName || ' ' || c.LastName AS CustomerName,
            c.Phone,
            c.Email,
            il.InvoiceLineId,
            il.UnitPrice,
            il.Quantity,
            t.Name  AS TrackName,
            ar.Name AS ArtistName,
            al.Title AS AlbumTitle
        FROM Invoice i
        JOIN Customer c ON i.CustomerId = c.CustomerId
        JOIN InvoiceLine il ON il.InvoiceId = i.InvoiceId
        JOIN Track t ON il.TrackId = t.TrackId
        JOIN Album al ON t.AlbumId = al.AlbumId
        JOIN Artist ar ON al.ArtistId = ar.ArtistId
        WHERE (c.FirstName LIKE ? OR c.LastName LIKE ?
               OR c.FirstName || ' ' || c.LastName LIKE ?
               OR c.Phone LIKE ?)
    """
    params: list[Any] = [pattern, pattern, pattern, pattern]

    if artist_or_track:
        art_pattern = f"%{artist_or_track}%"
        sql += " AND (ar.Name LIKE ? OR t.Name LIKE ?)"
        params += [art_pattern, art_pattern]

    sql += " ORDER BY i.InvoiceId, il.InvoiceLineId"

    try:
        conn = get_db()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    except Exception as e:
        return [types.TextContent(type="text", text=f"Database error: {e}")]

    if not rows:
        return [types.TextContent(type="text", text="No invoices found for that customer.")]

    # Group by invoice
    invoices: dict[int, dict] = {}
    for row in rows:
        inv_id = row["InvoiceId"]
        if inv_id not in invoices:
            invoices[inv_id] = {
                "invoice_id": inv_id,
                "date": row["InvoiceDate"],
                "total": row["Total"],
                "customer": row["CustomerName"],
                "phone": row["Phone"],
                "email": row["Email"],
                "lines": [],
            }
        invoices[inv_id]["lines"].append({
            "track": row["TrackName"],
            "artist": row["ArtistName"],
            "album": row["AlbumTitle"],
            "price": row["UnitPrice"],
            "qty": row["Quantity"],
        })

    result_lines = []
    for inv in invoices.values():
        result_lines.append(
            f"Invoice #{inv['invoice_id']} | {inv['date']} | Total: ${inv['total']:.2f}\n"
            f"  Customer: {inv['customer']} | {inv['phone']} | {inv['email']}"
        )
        for line in inv["lines"]:
            result_lines.append(
                f"    - {line['track']} by {line['artist']} ({line['album']}) "
                f"× {line['qty']} @ ${line['price']:.2f}"
            )

    return [types.TextContent(type="text", text="\n".join(result_lines))]


def _invoice_refund(args: dict) -> list[types.TextContent]:
    invoice_id = args.get("invoice_id")
    if not isinstance(invoice_id, int):
        return [types.TextContent(type="text", text="Error: invoice_id must be an integer.")]

    try:
        conn = get_db()
        row = conn.execute(
            "SELECT Total FROM Invoice WHERE InvoiceId = ?", [invoice_id]
        ).fetchone()

        if row is None:
            conn.close()
            return [types.TextContent(type="text", text=f"Error: Invoice #{invoice_id} not found.")]

        original_total = row["Total"]

        conn.execute("DELETE FROM InvoiceLine WHERE InvoiceId = ?", [invoice_id])
        conn.execute("UPDATE Invoice SET Total = 0.0 WHERE InvoiceId = ?", [invoice_id])
        conn.commit()
        conn.close()

        return [types.TextContent(
            type="text",
            text=f"Refund successful for Invoice #{invoice_id}. "
                 f"Amount refunded: ${original_total:.2f}. Invoice total set to $0.00.",
        )]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Refund error: {e}")]


# ── Starlette + Uvicorn (StreamableHTTPSessionManager — correct modern pattern) ─

session_manager = StreamableHTTPSessionManager(
    app=server,
    json_response=True,
    stateless=True,
)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with session_manager.run():
        yield


starlette_app = Starlette(
    routes=[Mount("/mcp", app=session_manager.handle_request)],
    lifespan=lifespan,
)

if __name__ == "__main__":
    uvicorn.run(starlette_app, host="0.0.0.0", port=MCP_PORT)
