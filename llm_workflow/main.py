"""
Assignment 3 — LangGraph Workflow
End-to-end orchestration: Intent classifier → QNA agent or Refund agent.

Flow:
  START → classify_node → route_intent
                            ├── "qna"     → qna_node    → END
                            ├── "refund"  → refund_node → END
                            └── "unknown" → interrupt() → human picks route → resume

Chạy:
    python main.py
"""

import os
import sqlite3
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

from dotenv import load_dotenv

from mcp_http_client import InvoiceMCPClient

# ── Load .env (ở thư mục gốc dự án) ─────────────────────────────────────────────
# Nạp NVIDIA_API_KEY, MCP_PORT... từ .env để không phải nhập tay vào terminal.
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Config ─────────────────────────────────────────────────────────────────────
MCP_PORT = int(os.environ.get("MCP_PORT", 8765))
DB_PATH = Path(__file__).parent.parent / "mcp-servers" / "invoice" / "data" / "chinook.db"
SKILL_PATH = Path(__file__).parent.parent / "qna_agent" / "skills" / "music-store-assistant" / "SKILL.md"


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm() -> ChatNVIDIA:
    return ChatNVIDIA(
        model="meta/llama-3.3-70b-instruct",
        api_key=os.environ.get("NVIDIA_API_KEY", ""),
        temperature=0.6,
        top_p=0.95,
        max_tokens=1024,
    )


def extract_content(response) -> str:
    """Lấy text từ response."""
    return (response.content or "").strip()


# ── State ──────────────────────────────────────────────────────────────────────

class ConversationState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    answer: str


# ── Nodes ─────────────────────────────────────────────────────────────────────

def classify_node(state: ConversationState) -> dict:
    """
    Phân loại ý định người dùng: qna, refund, hoặc unknown.
    Dùng text parsing thay vì structured output (Qwen không hỗ trợ).
    Nếu unknown → interrupt() để hỏi người dùng chọn hướng đi.
    """
    llm = get_llm()
    question = state["messages"][-1].content

    response = llm.invoke([
        SystemMessage(content=(
            "Classify the user's intent. Reply with ONLY one word: 'qna', 'refund', or 'unknown'.\n"
            "- 'qna': questions about music, artists, albums, tracks, catalog\n"
            "- 'refund': requests to refund, cancel, search/check invoices, billing\n"
            "- 'unknown': anything else\n"
            "Reply with exactly one word, nothing else."
        )),
        HumanMessage(content=question),
    ])

    # Parse text output — strip <think> của Qwen3.5, lấy từ đầu tiên
    clean = extract_content(response).lower()
    raw = clean.split()[0].strip(".,!?\"'") if clean.split() else "unknown"
    intent = raw if raw in ("qna", "refund") else "unknown"

    print(f"[classify_node] raw='{response.content.strip()}' -> intent={intent}")

    if intent == "unknown":
        chosen = interrupt(
            "Tôi không chắc bạn muốn làm gì. Bạn muốn:\n"
            "  1. Hỏi về âm nhạc/catalog (qna)\n"
            "  2. Hoàn tiền/tìm kiếm hóa đơn (refund)\n"
            "Nhập 'qna' hoặc 'refund': "
        )
        return {"intent": chosen.strip().lower()}

    return {"intent": intent}


def route_intent(state: ConversationState) -> Literal["qna_node", "refund_node"]:
    """Conditional edge: điều hướng dựa vào intent."""
    return "qna_node" if state["intent"] == "qna" else "refund_node"


def qna_node(state: ConversationState) -> dict:
    """
    QNA agent: dùng SKILL.md + Chinook DB để trả lời câu hỏi âm nhạc.
    Đọc skill (progressive disclosure) rồi query DB.
    """
    question = state["messages"][-1].content
    print(f"\n[qna_node] Question: {question}")

    # Load SKILL.md (progressive disclosure)
    skill_content = SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""

    # Query Chinook DB trực tiếp
    db_context = _query_chinook_for_context(question)

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=f"{skill_content}\n\nDatabase query results:\n{db_context}"),
        HumanMessage(content=question),
    ])

    answer = extract_content(response)
    return {
        "messages": [AIMessage(content=answer)],
        "answer": answer,
    }


def refund_node(state: ConversationState) -> dict:
    """
    Refund agent: kết nối Invoice MCP server để tìm và hoàn tiền invoice.
    """
    question = state["messages"][-1].content
    print(f"\n[refund_node] Request: {question}")

    mcp_client = InvoiceMCPClient()
    llm = get_llm()

    # Bước 1: Dùng LLM để extract tên khách hàng từ câu hỏi
    extract_result = llm.invoke([
        SystemMessage(content=(
            "Extract the customer name from the user message. "
            "Reply with ONLY the customer name, nothing else. "
            "Example: if user says 'refund for John Smith', reply 'John Smith'. "
            "If no name found, reply 'unknown'."
        )),
        HumanMessage(content=question),
    ])
    customer_name = extract_content(extract_result).strip().strip("'\"")
    print(f"[refund_node] Customer name extracted: {customer_name!r}")

    # Bước 2: Search invoices qua MCP dùng tên khách hàng đã extract
    search_query = customer_name if customer_name and customer_name != "unknown" else question[:50]
    search_result = mcp_client.invoice_search(customer_query=search_query)
    print(f"[refund_node] Search result:\n{search_result}")

    # Bước 3: Dùng LLM để quyết định có refund không và refund invoice nào
    decision = llm.invoke([
        SystemMessage(content=(
            "You are a refund agent. Based on the user request and invoice search results, "
            "determine if a refund should be processed. "
            "If yes, call invoice_refund with the correct invoice_id. "
            "If the invoice search returns no results, ask the user to provide more details."
        )),
        HumanMessage(content=f"User request: {question}\n\nInvoice search results:\n{search_result}"),
    ])

    # Check if we should auto-refund (simple heuristic: if exactly one invoice found)
    lines = search_result.strip().split("\n")
    invoice_ids = [
        int(line.split("#")[1].split("|")[0].strip())
        for line in lines if line.startswith("Invoice #")
    ]

    if len(invoice_ids) == 1:
        refund_result = mcp_client.invoice_refund(invoice_ids[0])
        answer = f"{refund_result}\n\n(Details: {decision.content})"
    else:
        answer = decision.content
        if invoice_ids:
            answer += f"\n\nFound {len(invoice_ids)} invoices: {invoice_ids}. Please specify which invoice to refund."

    return {
        "messages": [AIMessage(content=answer)],
        "answer": answer,
    }


# ── Chinook DB helper ─────────────────────────────────────────────────────────

def _query_chinook_for_context(question: str) -> str:
    """Lấy context từ Chinook DB dựa vào câu hỏi (simple keyword search)."""
    if not DB_PATH.exists():
        return "Database not found."

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Lấy artists, albums, tracks liên quan
        keywords = [w for w in question.lower().split() if len(w) > 3]
        results = []

        for kw in keywords[:3]:  # max 3 keywords
            pattern = f"%{kw}%"
            rows = conn.execute("""
                SELECT ar.Name AS Artist, al.Title AS Album, t.Name AS Track, t.UnitPrice
                FROM Track t
                JOIN Album al ON t.AlbumId = al.AlbumId
                JOIN Artist ar ON al.ArtistId = ar.ArtistId
                WHERE ar.Name LIKE ? OR al.Title LIKE ? OR t.Name LIKE ?
                LIMIT 10
            """, [pattern, pattern, pattern]).fetchall()
            results.extend([dict(r) for r in rows])

        conn.close()

        if not results:
            # Return full catalog summary
            conn = sqlite3.connect(str(DB_PATH))
            artists = conn.execute("SELECT Name FROM Artist ORDER BY Name").fetchall()
            conn.close()
            return "Available artists: " + ", ".join(r[0] for r in artists)

        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            key = (r["Artist"], r["Album"], r["Track"])
            if key not in seen:
                seen.add(key)
                unique.append(r)

        lines = [f"- {r['Artist']} | {r['Album']} | {r['Track']} (${r['UnitPrice']:.2f})" for r in unique[:20]]
        return "\n".join(lines)

    except Exception as e:
        return f"DB error: {e}"


# ── Build Graph ────────────────────────────────────────────────────────────────

def build_graph():
    checkpointer = InMemorySaver()
    builder = StateGraph(ConversationState)

    builder.add_node("classify_node", classify_node)
    builder.add_node("qna_node", qna_node)
    builder.add_node("refund_node", refund_node)

    builder.add_edge(START, "classify_node")
    builder.add_conditional_edges("classify_node", route_intent, {
        "qna_node": "qna_node",
        "refund_node": "refund_node",
    })
    builder.add_edge("qna_node", END)
    builder.add_edge("refund_node", END)

    return builder.compile(checkpointer=checkpointer)


# ── CLI ────────────────────────────────────────────────────────────────────────

def run():
    import getpass

    if not os.environ.get("NVIDIA_API_KEY", "").startswith("nvapi-"):
        key = getpass.getpass("NVIDIA API key: ")
        os.environ["NVIDIA_API_KEY"] = key

    graph = build_graph()
    thread_id = "session-1"
    config = {"configurable": {"thread_id": thread_id}}

    print("\n" + "=" * 60)
    print("  Music Store Agent — gõ 'exit' để thoát")
    print("=" * 60)
    print("  Thử hỏi: 'What albums does AC/DC have?'")
    print("           'I want to refund invoice for Leonie Kohler'")

    while True:
        try:
            question = input("\n❓  Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if question.lower() in ("exit", "quit", "q"):
            break
        if not question:
            continue

        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=question)], "intent": "", "answer": ""},
                config=config,
            )

            # Handle interrupt (unknown intent)
            if "__interrupt__" in result:
                prompt_msg = result["__interrupt__"][0].value
                print(f"\n🤔  {prompt_msg}", end="")
                user_choice = input().strip()
                result = graph.invoke(
                    Command(resume=user_choice),
                             config=config,
                )

            answer = result.get("answer", "")
            if answer:
                print(f"\n💬  Agent: {answer}")

        except Exception as e:
            print(f"\n[Error] {e}")


if __name__ == "__main__":
    run()
