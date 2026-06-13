"""
Streamlit demo — Music Store Agent
Một giao diện, chọn 1 trong 2 luồng (LangGraph / NeMo Agent Toolkit) và
VISUALIZE đường chạy qua các node theo thời gian thực (graph được tô màu dần).

Chạy:
    # Terminal 1: MCP server (bắt buộc)
    python mcp-servers/invoice/src/mcp_server_invoice/server_http.py
    # Terminal 2:
    streamlit run app.py
"""

import asyncio
import sys
import time
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

# stdout cp1252 trên Windows làm print() ký tự Unicode (tiếng Việt, ->) bị crash.
# Ép utf-8 + bỏ qua lỗi để node nào in gì cũng an toàn.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "llm_workflow"))  # để import main.py + mcp_http_client.py

NAT_CONFIG = str(ROOT / "nemo_agent_toolkit" / "workflow.yaml")
MCP_URL = "http://127.0.0.1:8765/mcp/"

st.set_page_config(page_title="Music Store Agent — LangGraph vs NAT", layout="wide")


# ── Định nghĩa graph tĩnh cho mỗi luồng ─────────────────────────────────────────
# (id, nhãn, hình dạng)
LG_NODES = [
    ("__start__", "START", "oval"),
    ("classify_node", "classify_node\n(phân loại ý định)", "box"),
    ("qna_node", "qna_node\n(hỏi đáp catalog · SQLite)", "box"),
    ("refund_node", "refund_node\n(hoàn tiền · MCP)", "box"),
    ("__end__", "END", "oval"),
]
LG_EDGES = [
    ("__start__", "classify_node"),
    ("classify_node", "qna_node"),
    ("classify_node", "refund_node"),
    ("qna_node", "__end__"),
    ("refund_node", "__end__"),
]

NAT_NODES = [
    ("START", "START", "oval"),
    ("agent", "agent\n(ReAct · llama-3.3)", "box"),
    ("invoice_search", "invoice_search\n(tool MCP)", "box"),
    ("invoice_refund", "invoice_refund\n(tool MCP)", "box"),
    ("END", "Final Answer", "oval"),
]
NAT_EDGES = [
    ("START", "agent"),
    ("agent", "invoice_search"),
    ("agent", "invoice_refund"),
    ("invoice_search", "agent"),
    ("invoice_refund", "agent"),
    ("agent", "END"),
]


# ── Vẽ graph (DOT) với node/cạnh được highlight ─────────────────────────────────

def build_dot(nodes, edges, active_nodes, active_edges, current=None):
    lines = [
        "digraph G {",
        '  rankdir=TB;',
        '  bgcolor="transparent";',
        '  node [fontname="Segoe UI", fontsize=11];',
        '  edge [fontname="Segoe UI", fontsize=9, color="#9ca3af"];',
    ]
    for nid, label, shape in nodes:
        esc = label.replace("\n", "\\n")
        if nid == current:                       # node đang chạy → cam, viền đậm
            style = 'style="filled,bold", fillcolor="#f59e0b", fontcolor="white", color="#b45309", penwidth=2.5'
        elif nid in active_nodes:                # đã chạy qua → xanh
            style = 'style=filled, fillcolor="#22c55e", fontcolor="white", color="#16a34a"'
        else:                                    # chưa chạy → xám
            style = 'style=filled, fillcolor="#e5e7eb", fontcolor="#374151", color="#d1d5db"'
        lines.append(f'  "{nid}" [label="{esc}", shape={shape}, {style}];')
    for src, dst in edges:
        if (src, dst) in active_edges:
            lines.append(f'  "{src}" -> "{dst}" [color="#16a34a", penwidth=2.5];')
        else:
            lines.append(f'  "{src}" -> "{dst}";')
    lines.append("}")
    return "\n".join(lines)


def edges_from_path(ordered):
    return {(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)}


def animate_path(placeholder, ordered, nodes, edges, delay=0.7):
    """Tô màu dần theo thứ tự node chạy."""
    for i in range(len(ordered)):
        active_nodes = set(ordered[: i + 1])
        active_edges = edges_from_path(ordered[: i + 1])
        current = ordered[i]
        dot = build_dot(nodes, edges, active_nodes, active_edges, current=current)
        placeholder.graphviz_chart(dot, width="stretch")
        time.sleep(delay)
    # khung cuối: tất cả node đã qua là xanh (không còn "current")
    dot = build_dot(nodes, edges, set(ordered), edges_from_path(ordered))
    placeholder.graphviz_chart(dot, width="stretch")


def static_path(placeholder, ordered, nodes, edges):
    placeholder.graphviz_chart(
        build_dot(nodes, edges, set(ordered), edges_from_path(ordered)),
        width="stretch",
    )


# ── MCP health ──────────────────────────────────────────────────────────────────

def mcp_alive():
    try:
        r = requests.post(
            MCP_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
            timeout=3,
        )
        return r.status_code < 500
    except Exception:
        return False


# ── Luồng LangGraph ─────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_lg_graph():
    import main as lg  # llm_workflow/main.py
    return lg.build_graph()


def run_langgraph(question, thread_id):
    """Trả về dict: status='answer'|'interrupt', ..."""
    from langchain_core.messages import HumanMessage
    graph = get_lg_graph()
    cfg = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {"messages": [HumanMessage(content=question)], "intent": "", "answer": ""},
        config=cfg,
    )
    if "__interrupt__" in result:
        return {"status": "interrupt", "prompt": result["__interrupt__"][0].value, "thread_id": thread_id}
    return _lg_finish(result)


def resume_langgraph(choice, thread_id):
    from langgraph.types import Command
    graph = get_lg_graph()
    cfg = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(Command(resume=choice), config=cfg)
    return _lg_finish(result)


def _lg_finish(result):
    intent = result.get("intent", "")
    branch = "qna_node" if intent == "qna" else "refund_node"
    ordered = ["__start__", "classify_node", branch, "__end__"]
    answer = result.get("answer") or (result["messages"][-1].content if result.get("messages") else "")
    return {
        "status": "answer",
        "ordered": ordered,
        "answer": answer,
        "trace": [f"Ý định được phân loại: **{intent or '?'}** → đi nhánh `{branch}`"],
    }


# ── Luồng NAT (in-process + bắt intermediate steps) ─────────────────────────────

def run_nat(question):
    async def _go():
        from nat.runtime.loader import load_workflow
        steps = []
        async with load_workflow(NAT_CONFIG) as sm:
            async with sm.run(question) as runner:
                sub = runner.context.intermediate_step_manager.subscribe(
                    lambda s: steps.append((str(s.payload.event_type), s.payload.name))
                )
                result = await runner.result(to_type=str)
                sub.unsubscribe()
        return result, steps

    loop = asyncio.new_event_loop()
    try:
        result, steps = loop.run_until_complete(_go())
    finally:
        loop.close()

    # Trích tool đã gọi (theo thứ tự)
    tools = []
    for et, name in steps:
        if "FUNCTION_START" in et and name and name.startswith("mcp_invoice__"):
            tools.append("invoice_refund" if "refund" in name else "invoice_search")

    ordered = ["START", "agent"]
    for t in tools:
        ordered += [t, "agent"]
    ordered.append("END")

    trace = [f"🔧 Agent gọi tool `{t}`" for t in tools] or ["Agent trả lời trực tiếp (không gọi tool)."]
    return {"status": "answer", "ordered": ordered, "answer": result, "trace": trace}


# ════════════════════════════════════════════════════════════════════════════════
#  UI
# ════════════════════════════════════════════════════════════════════════════════

st.title("🎵 Music Store Agent — LangGraph vs NeMo Agent Toolkit")

with st.sidebar:
    st.header("⚙️ Cấu hình")
    flow = st.radio("Chọn luồng:", ["LangGraph", "NeMo Agent Toolkit (NAT)"])
    animate = st.toggle("Animate đường chạy", value=True)
    st.divider()
    st.caption("Trạng thái dịch vụ")
    st.write("🟢 MCP server (8765)" if mcp_alive() else "🔴 MCP server (8765) — chưa chạy")
    key_ok = bool(__import__("os").environ.get("NVIDIA_API_KEY", "").startswith("nvapi-"))
    st.write("🟢 NVIDIA_API_KEY" if key_ok else "🔴 NVIDIA_API_KEY — thiếu trong .env")
    st.divider()
    st.caption(
        "Gợi ý câu hỏi:\n"
        "- Search invoices for Bjorn Hansen\n"
        "- Find invoices for Helena Holy\n"
        "- Refund invoice 3\n"
        "- What albums does AC/DC have? (LangGraph)"
    )

# state
st.session_state.setdefault("history", [])      # [{role, content}]
st.session_state.setdefault("last_run", None)    # {flow, ordered, ...}
st.session_state.setdefault("pending", None)     # interrupt đang chờ {thread_id, prompt}
st.session_state.setdefault("tid", 0)
st.session_state.setdefault("animate_next", False)

col_chat, col_graph = st.columns([0.52, 0.48])

# ── Cột graph ───────────────────────────────────────────────────────────────────
with col_graph:
    st.subheader("🗺️ Đường chạy")
    nodes, edges = (LG_NODES, LG_EDGES) if flow == "LangGraph" else (NAT_NODES, NAT_EDGES)
    graph_ph = st.empty()
    lr = st.session_state["last_run"]
    if lr and lr["flow"] == flow:
        static_path(graph_ph, lr["ordered"], nodes, edges)
    else:
        graph_ph.graphviz_chart(build_dot(nodes, edges, set(), set()), width="stretch")
    st.caption("🟠 đang chạy · 🟢 đã qua · ⚪ chưa chạy")

# ── Cột chat ────────────────────────────────────────────────────────────────────
with col_chat:
    st.subheader(f"💬 Chat — {flow}")

    for m in st.session_state["history"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Xử lý interrupt (LangGraph, intent unknown)
    if st.session_state["pending"]:
        p = st.session_state["pending"]
        st.info(p["prompt"])
        choice = st.radio("Chọn nhánh:", ["qna", "refund"], horizontal=True, key="resume_choice")
        if st.button("➡️ Tiếp tục"):
            with st.spinner("Đang chạy tiếp..."):
                out = resume_langgraph(choice, p["thread_id"])
            st.session_state["pending"] = None
            st.session_state["history"].append({"role": "assistant", "content": out["answer"]})
            st.session_state["last_run"] = {"flow": flow, **out}
            st.session_state["animate_next"] = True
            st.rerun()

    question = st.chat_input("Nhập câu hỏi...")
    if question and not st.session_state["pending"]:
        st.session_state["history"].append({"role": "user", "content": question})
        try:
            if flow == "LangGraph":
                st.session_state["tid"] += 1
                tid = f"t{st.session_state['tid']}"
                with st.spinner("LangGraph đang chạy..."):
                    out = run_langgraph(question, tid)
                if out["status"] == "interrupt":
                    st.session_state["pending"] = {"thread_id": tid, "prompt": out["prompt"]}
                    st.rerun()
            else:
                with st.spinner("NAT (ReAct) đang chạy..."):
                    out = run_nat(question)

            st.session_state["history"].append({"role": "assistant", "content": out["answer"]})
            st.session_state["last_run"] = {"flow": flow, **out}
            st.session_state["animate_next"] = True
            st.rerun()
        except Exception as e:
            st.session_state["history"].append({"role": "assistant", "content": f"❌ Lỗi: {e}"})
            st.rerun()

    # Trace của lần chạy gần nhất
    lr = st.session_state["last_run"]
    if lr and lr["flow"] == flow and lr.get("trace"):
        with st.expander("🔍 Chi tiết đường chạy", expanded=True):
            for line in lr["trace"]:
                st.markdown("- " + line)

# ── Animate (chạy sau khi layout đã dựng) ───────────────────────────────────────
if st.session_state["animate_next"]:
    st.session_state["animate_next"] = False
    lr = st.session_state["last_run"]
    if lr and lr["flow"] == flow and animate:
        animate_path(graph_ph, lr["ordered"], nodes, edges)
