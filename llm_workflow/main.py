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

import json
import os
import re
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
    Phân loại ý định: qna / search / refund / unknown.
    Dùng text parsing thay vì structured output (Qwen không hỗ trợ).
    Nếu unknown → interrupt() để hỏi người dùng chọn hướng đi.

    Lưu ý: 'search' (tra cứu, CHỈ ĐỌC) tách khỏi 'refund' (ghi DB, hoàn tiền) —
    khớp 2 tool riêng của MCP server (invoice_search vs invoice_refund), tránh
    việc một câu "tìm hóa đơn" lại vô tình kích hoạt hoàn tiền.
    """
    llm = get_llm()
    question = state["messages"][-1].content

    response = llm.invoke([
        SystemMessage(content=(
            "Classify the user's intent. Reply with ONLY one word: "
            "'qna', 'search', 'refund', or 'unknown'.\n"
            "- 'qna': questions about the music catalog (artists, albums, tracks, prices)\n"
            "- 'search': look up / find / show / list / check EXISTING invoices "
            "(read-only, NO money returned)\n"
            "- 'refund': refund / cancel / return money for an invoice\n"
            "- 'unknown': anything else\n"
            "Reply with exactly one word, nothing else."
        )),
        HumanMessage(content=question),
    ])

    # Parse text output — strip <think> của Qwen3.5, lấy từ đầu tiên
    clean = extract_content(response).lower()
    raw = clean.split()[0].strip(".,!?\"'") if clean.split() else "unknown"
    intent = raw if raw in ("qna", "search", "refund") else "unknown"

    print(f"[classify_node] raw='{response.content.strip()}' -> intent={intent}")

    if intent == "unknown":
        chosen = interrupt(
            "Tôi không chắc bạn muốn làm gì. Bạn muốn:\n"
            "  1. Hỏi về âm nhạc/catalog (qna)\n"
            "  2. Tra cứu hóa đơn (search)\n"
            "  3. Hoàn tiền hóa đơn (refund)\n"
            "Nhập 'qna', 'search' hoặc 'refund': "
        )
        return {"intent": chosen.strip().lower()}

    return {"intent": intent}


def route_intent(state: ConversationState) -> Literal["qna_node", "search_node", "refund_node"]:
    """Conditional edge: điều hướng dựa vào intent."""
    return {"qna": "qna_node", "search": "search_node"}.get(state["intent"], "refund_node")


def qna_node(state: ConversationState) -> dict:
    """
    QNA agent (text-to-SQL THẬT): nạp SKILL.md → LLM sinh SQL → app THỰC THI
    (chỉ SELECT, read-only) → LLM diễn giải từ KẾT QUẢ THẬT.

    Trước đây node này chỉ "giả lập" bằng keyword search → LLM bịa kết quả.
    Giờ SQL được chạy thật nên câu trả lời bám đúng dữ liệu trong DB.
    """
    question = state["messages"][-1].content
    print(f"\n[qna_node] Question: {question}")

    skill_content = SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""
    llm = get_llm()

    # Bước 1: LLM sinh SQL (theo schema + conventions trong SKILL.md)
    sql = _generate_sql(llm, skill_content, question)
    print(f"[qna_node] SQL sinh ra:\n{sql}")

    # Bước 2: Thực thi an toàn (chỉ SELECT)
    if not _is_safe_select(sql):
        answer = (
            "Tôi chỉ hỗ trợ truy vấn **đọc dữ liệu (SELECT)** cho catalog âm nhạc. "
            "Vui lòng đặt câu hỏi về nghệ sĩ / album / track."
        )
        return {"messages": [AIMessage(content=answer)], "answer": answer}

    cols, rows, err = _run_select(sql)
    if err:
        print(f"[qna_node] Lỗi SQL: {err}")
        answer = f"Truy vấn lỗi: {err}\n\nSQL đã thử:\n```sql\n{sql}\n```"
        return {"messages": [AIMessage(content=answer)], "answer": answer}
    print(f"[qna_node] Số dòng trả về: {len(rows)}")

    # Bước 3: LLM diễn giải CHỈ từ kết quả thật (chống bịa)
    rows_json = json.dumps(rows, ensure_ascii=False)
    response = llm.invoke([
        SystemMessage(content=(
            "You are a music store assistant. Answer the user's question using ONLY the SQL "
            "result rows provided below — do NOT use any outside knowledge or invent data. "
            "If the rows are empty, clearly say no matching results were found. "
            "Show the SQL that was run, then present the results clearly (bullets/table)."
        )),
        HumanMessage(content=(
            f"Question: {question}\n\n"
            f"SQL executed:\n{sql}\n\n"
            f"Result columns: {list(cols)}\n"
            f"Result rows (JSON, authoritative — the ONLY source of truth):\n{rows_json}"
        )),
    ])

    answer = extract_content(response)
    return {
        "messages": [AIMessage(content=answer)],
        "answer": answer,
    }


def search_node(state: ConversationState) -> dict:
    """
    Search agent (CHỈ ĐỌC): gọi tool MCP invoice_search để tra cứu hóa đơn theo
    tên/điện thoại khách hàng. KHÔNG bao giờ ghi DB (không refund) — tách bạch
    hoàn toàn với refund_node, khớp 2 tool riêng của MCP server.
    """
    question = state["messages"][-1].content
    print(f"\n[search_node] Request: {question}")

    mcp_client = InvoiceMCPClient()
    customer_name = _extract_customer_name(get_llm(), question)
    print(f"[search_node] Customer extracted: {customer_name!r}")

    if not customer_name:
        answer = (
            "Bạn muốn tra cứu hóa đơn của khách hàng nào? "
            "Vui lòng cho biết **tên** hoặc **số điện thoại** khách hàng."
        )
        return {"messages": [AIMessage(content=answer)], "answer": answer}

    result = mcp_client.invoice_search(customer_query=customer_name)
    print(f"[search_node] Search result:\n{result}")
    answer = f"Kết quả tra cứu cho '{customer_name}':\n\n{result}"
    return {"messages": [AIMessage(content=answer)], "answer": answer}


def refund_node(state: ConversationState) -> dict:
    """
    Refund agent: kết nối Invoice MCP server để tìm và hoàn tiền invoice.

    Hai chiến lược (chọn theo nội dung câu hỏi — KHÔNG tách thành 2 graph node,
    vì "by id" / "by customer" chỉ là 2 cách thực hiện cùng ý định 'refund'):
      • Có số hóa đơn rõ ràng (vd "refund invoice 3") → refund thẳng theo invoice_id.
      • Chỉ có tên khách hàng (vd "refund for Francois Tremblay") → tìm hóa đơn
        của khách rồi refund nếu xác định được duy nhất 1 hóa đơn còn hiệu lực.
    """
    question = state["messages"][-1].content
    print(f"\n[refund_node] Request: {question}")

    mcp_client = InvoiceMCPClient()

    invoice_id = _extract_invoice_id(question)
    if invoice_id is not None:
        print(f"[refund_node] Strategy = by invoice_id ({invoice_id})")
        answer = _refund_by_invoice_id(mcp_client, invoice_id)
    else:
        print("[refund_node] Strategy = by customer name")
        answer = _refund_by_customer(mcp_client, get_llm(), question)

    print(f"[refund_node] Answer: {answer}")
    return {
        "messages": [AIMessage(content=answer)],
        "answer": answer,
    }


# Bắt số hóa đơn rõ ràng: "invoice 3", "invoice #3", "hóa đơn 3", "#3".
_INVOICE_ID_RE = re.compile(
    r"(?:invoice|h[oó]a\s*[đd][oơ]n|#)\s*#?\s*(\d+)", re.IGNORECASE
)
# Bắt id hóa đơn trong từng dòng kết quả search: "Invoice #4 | ... | Total: $7.92  [REFUNDED...]"
_SEARCH_LINE_RE = re.compile(r"Invoice #(\d+)\b.*Total:\s*\$([\d.]+)")


def _extract_invoice_id(text: str) -> int | None:
    """Trả về invoice_id nếu người dùng nêu rõ số hóa đơn, ngược lại None."""
    m = _INVOICE_ID_RE.search(text)
    return int(m.group(1)) if m else None


def _extract_customer_name(llm, question: str) -> str:
    """Trích tên khách hàng bằng LLM; trả "" nếu không có (dùng cho search & refund)."""
    resp = llm.invoke([
        SystemMessage(content=(
            "Extract the customer name from the user message. "
            "Reply with ONLY the customer name, nothing else. "
            "Example: if user says 'refund for John Smith', reply 'John Smith'. "
            "If no name found, reply 'unknown'."
        )),
        HumanMessage(content=question),
    ])
    name = extract_content(resp).strip().strip("'\"")
    return "" if name.lower() == "unknown" else name


def _refund_by_invoice_id(mcp_client: InvoiceMCPClient, invoice_id: int) -> str:
    """Refund trực tiếp theo invoice_id. Server tự báo: not found / đã refund / thành công."""
    result = mcp_client.invoice_refund(invoice_id)
    print(f"[refund_node] Refund result: {result}")
    return result


def _refund_by_customer(mcp_client: InvoiceMCPClient, llm, question: str) -> str:
    """Tìm hóa đơn theo tên khách, refund nếu xác định được duy nhất 1 hóa đơn còn hiệu lực."""
    customer_name = _extract_customer_name(llm, question)
    print(f"[refund_node] Customer name extracted: {customer_name!r}")

    if not customer_name:
        return (
            "Bạn muốn hoàn tiền hóa đơn nào? Vui lòng cho biết **số hóa đơn** "
            "(vd: 'refund invoice 3') hoặc **tên khách hàng** (vd: 'refund for Francois Tremblay')."
        )

    search_result = mcp_client.invoice_search(customer_query=customer_name)
    print(f"[refund_node] Search result:\n{search_result}")

    if search_result.startswith("No customer found"):
        return (
            f"Không tìm thấy khách hàng khớp '{customer_name}'. "
            "Vui lòng kiểm tra lại tên, hoặc cung cấp số hóa đơn cần hoàn."
        )

    # Phân tích các hóa đơn từ kết quả search (kèm trạng thái đã refund).
    parsed = [
        (int(m.group(1)), float(m.group(2)), "[REFUNDED" in line)
        for line in search_result.splitlines()
        if (m := _SEARCH_LINE_RE.search(line))
    ]
    refundable = [iid for (iid, _total, refunded) in parsed if not refunded]

    if not parsed:
        return f"Khách hàng '{customer_name}' tồn tại nhưng chưa có hóa đơn nào."
    if not refundable:
        return (
            f"Tất cả hóa đơn của '{customer_name}' đã được hoàn tiền trước đó "
            f"(các hóa đơn: {[iid for iid, _t, _r in parsed]})."
        )
    if len(refundable) == 1:
        return _refund_by_invoice_id(mcp_client, refundable[0])

    return (
        f"Khách hàng '{customer_name}' có {len(refundable)} hóa đơn còn hiệu lực: {refundable}. "
        "Vui lòng cho biết **số hóa đơn** cần hoàn (vd: 'refund invoice 3')."
    )


# ── Text-to-SQL helpers (qna_node) ───────────────────────────────────────────

# Từ khóa ghi dữ liệu / nguy hiểm — cấm trong nhánh QnA (chỉ cho đọc).
_FORBIDDEN_SQL = (
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "truncate",
)


def _generate_sql(llm, skill_content: str, question: str) -> str:
    """Yêu cầu LLM sinh DUY NHẤT một câu SELECT (theo schema trong SKILL.md)."""
    resp = llm.invoke([
        SystemMessage(content=(
            skill_content
            + "\n\n---\nReturn ONLY a single SQLite SELECT statement that answers the "
            "question, using the schema above. No explanation, no prose, no markdown "
            "fences — just the SQL. It MUST be read-only (start with SELECT or WITH)."
        )),
        HumanMessage(content=question),
    ])
    return _extract_sql(extract_content(resp))


def _extract_sql(text: str) -> str:
    """Bóc SQL ra khỏi <think>…</think> / ```sql fences / prose dư thừa."""
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    m = re.search(r"```(?:sql)?\s*(.*?)```", t, flags=re.S | re.I)
    if m:
        t = m.group(1).strip()
    # nếu còn lẫn prose, lấy từ SELECT/WITH đầu tiên trở đi
    m2 = re.search(r"(?is)\b(select|with)\b.*", t)
    if m2:
        t = m2.group(0)
    return t.strip().rstrip(";").strip()


def _is_safe_select(sql: str) -> bool:
    """Chỉ cho phép 1 câu SELECT/WITH, không chứa từ khóa ghi, không nhiều statement."""
    if not sql:
        return False
    low = sql.lower().strip()
    if not (low.startswith("select") or low.startswith("with")):
        return False
    if ";" in sql.strip().rstrip(";"):       # nhiều statement
        return False
    return not any(re.search(rf"\b{kw}\b", low) for kw in _FORBIDDEN_SQL)


def _run_select(sql: str):
    """Chạy SELECT trên kết nối READ-ONLY. Trả (columns, rows, error)."""
    if not DB_PATH.exists():
        return [], [], "Database not found."
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql)
            fetched = cur.fetchall()
        finally:
            conn.close()
        cols = list(fetched[0].keys()) if fetched else (
            [d[0] for d in cur.description] if cur.description else []
        )
        return cols, [dict(r) for r in fetched], None
    except Exception as e:
        return [], [], str(e)


# ── Build Graph ────────────────────────────────────────────────────────────────

def build_graph():
    checkpointer = InMemorySaver()
    builder = StateGraph(ConversationState)

    builder.add_node("classify_node", classify_node)
    builder.add_node("qna_node", qna_node)
    builder.add_node("search_node", search_node)
    builder.add_node("refund_node", refund_node)

    builder.add_edge(START, "classify_node")
    builder.add_conditional_edges("classify_node", route_intent, {
        "qna_node": "qna_node",
        "search_node": "search_node",
        "refund_node": "refund_node",
    })
    builder.add_edge("qna_node", END)
    builder.add_edge("search_node", END)
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
