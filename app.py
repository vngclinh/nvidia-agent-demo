"""
Streamlit demo — Music Store Agent
Một giao diện, chọn 1 trong 2 luồng (LangGraph / NeMo Agent Toolkit) và
VISUALIZE đường chạy qua các node theo thời gian thực (graph được tô màu dần).

Tính năng deploy:
  • Tự khởi động MCP server (subprocess) — không cần terminal riêng.
  • Gating: yêu cầu người dùng nhập NVIDIA_API_KEY trước khi dùng.
  • Reset DB về bản gốc mỗi khi app khởi động (dữ liệu demo luôn nguyên vẹn).

Chạy local:
    streamlit run app.py
"""

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

# stdout cp1252 trên Windows làm print() ký tự Unicode (tiếng Việt, ->) bị crash.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "llm_workflow"))  # để import main.py + mcp_http_client.py

NAT_CONFIG = str(ROOT / "nemo_agent_toolkit" / "workflow.yaml")
MCP_PORT = int(os.environ.get("MCP_PORT", 8765))
MCP_URL = f"http://127.0.0.1:{MCP_PORT}/mcp/"
MCP_SERVER = str(ROOT / "mcp-servers" / "invoice" / "src" / "mcp_server_invoice" / "server_http.py")
DB_PATH = ROOT / "mcp-servers" / "invoice" / "data" / "chinook.db"
DB_SEED = ROOT / "mcp-servers" / "invoice" / "data" / "chinook.seed.db"
NVIDIA_BUILD_URL = "https://build.nvidia.com/meta/llama-3_3-70b-instruct"

st.set_page_config(
    page_title="Music Store Agent — LangGraph vs NAT",
    page_icon="🎵",
    layout="wide",
)


# ════════════════════════════════════════════════════════════════════════════════
#  THEME / CSS
# ════════════════════════════════════════════════════════════════════════════════

st.markdown(
    """
    <style>
      /* nền & font */
      .stApp { background: radial-gradient(1200px 600px at 50% -10%, #1a2740 0%, #0d1117 55%); }
      html, body, [class*="css"] { font-family: "Segoe UI", system-ui, sans-serif; }

      /* hero header */
      .hero {
        background: linear-gradient(110deg, #76b900 0%, #1f6feb 100%);
        border-radius: 18px; padding: 22px 28px; margin-bottom: 8px;
        box-shadow: 0 10px 30px rgba(0,0,0,.35);
      }
      .hero h1 { color: #fff; margin: 0; font-size: 1.7rem; font-weight: 700; letter-spacing: .2px; }
      .hero p  { color: #eaf5d8; margin: 6px 0 0; font-size: .95rem; }

      /* pill trạng thái */
      .pill { display:inline-flex; align-items:center; gap:7px; padding:5px 12px;
              border-radius:999px; font-size:.82rem; font-weight:600; margin:3px 0; }
      .pill.ok  { background:#10331b; color:#5ee08a; border:1px solid #1f7a45; }
      .pill.bad { background:#3a1518; color:#ff8b8b; border:1px solid #7a2230; }

      /* card */
      .card { background:#161b22ee; border:1px solid #283041; border-radius:14px;
              padding:16px 18px; box-shadow: 0 6px 18px rgba(0,0,0,.25); }

      /* graph legend */
      .legend { color:#9aa7b8; font-size:.83rem; }

      /* key gate */
      .gate { max-width: 720px; margin: 4vh auto 0; }
      .gate .stTextInput input { font-size: 1rem; }
      .steps { color:#c9d4e3; line-height: 1.7; }
      .steps code { background:#1f2733; padding:2px 7px; border-radius:6px; color:#9ecbff; }

      /* nút */
      .stButton>button { border-radius:10px; font-weight:600; }
      [data-testid="stChatInput"] { border-radius: 12px; }
      section[data-testid="stSidebar"] { background:#0e131b; border-right:1px solid #1d2531; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ════════════════════════════════════════════════════════════════════════════════
#  HẠ TẦNG: MCP server, reset DB, health
# ════════════════════════════════════════════════════════════════════════════════

def mcp_alive() -> bool:
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


@st.cache_resource(show_spinner="Đang khởi động MCP server...")
def ensure_mcp_server():
    """Tự spawn MCP server nếu chưa chạy (chạy 1 lần cho mỗi tiến trình app)."""
    if mcp_alive():
        return {"spawned": False}
    proc = subprocess.Popen(
        [sys.executable, MCP_SERVER],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(ROOT),
    )
    for _ in range(30):
        if mcp_alive():
            return {"spawned": True, "pid": proc.pid}
        time.sleep(0.5)
    return {"spawned": True, "pid": proc.pid, "warning": "MCP server chưa phản hồi sau 15s"}


@st.cache_resource(show_spinner=False)
def reset_db_once():
    """Reset DB về bản gốc (seed) — chạy 1 lần lúc app khởi động."""
    if DB_SEED.exists():
        shutil.copy(DB_SEED, DB_PATH)
        return True
    return False


def reset_db_now() -> bool:
    """Reset thủ công (nút bấm)."""
    if DB_SEED.exists():
        shutil.copy(DB_SEED, DB_PATH)
        return True
    return False


# chạy hạ tầng (cache → chỉ 1 lần / tiến trình)
_mcp = ensure_mcp_server()
_db_reset = reset_db_once()


# ════════════════════════════════════════════════════════════════════════════════
#  GATING: nhập NVIDIA API key
# ════════════════════════════════════════════════════════════════════════════════

def _key_valid(k: str) -> bool:
    return bool(k) and k.strip().startswith("nvapi-") and len(k.strip()) > 12


def require_api_key():
    """Nếu chưa có key hợp lệ → hiện màn hình nhập key và dừng app."""
    # ưu tiên key đã nhập trong session, sau đó tới .env / secrets
    key = st.session_state.get("nvidia_key") or os.environ.get("NVIDIA_API_KEY", "")
    if _key_valid(key):
        os.environ["NVIDIA_API_KEY"] = key.strip()
        st.session_state["nvidia_key"] = key.strip()
        return

    # ── Màn hình gate ──
    st.markdown('<div class="gate">', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero"><h1>🎵 Music Store Agent</h1>'
        '<p>LangGraph · NeMo Agent Toolkit · MCP — demo agent cửa hàng nhạc</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("### 🔑 Nhập NVIDIA API key để bắt đầu")
    st.markdown(
        f"""
        <div class="steps">
        Demo dùng mô hình <b>meta/llama-3.3-70b-instruct</b> qua NVIDIA NIM (miễn phí).
        Lấy key của bạn trong 30 giây:
        <ol>
          <li>Mở <a href="{NVIDIA_BUILD_URL}" target="_blank">build.nvidia.com/meta/llama-3_3-70b-instruct</a></li>
          <li>Đăng nhập → bấm <b>Get API Key</b> (hoặc <b>Build with this NIM</b>).</li>
          <li>Sao chép key dạng <code>nvapi-xxxxxxxx...</code> và dán vào ô bên dưới.</li>
        </ol>
        Key chỉ lưu trong phiên trình duyệt của bạn — không được ghi ra đĩa hay chia sẻ.
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("key_form", clear_on_submit=False):
        entered = st.text_input(
            "NVIDIA API key", type="password", placeholder="nvapi-...",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("🚀 Bắt đầu", width="stretch")
    if submitted:
        if _key_valid(entered):
            st.session_state["nvidia_key"] = entered.strip()
            os.environ["NVIDIA_API_KEY"] = entered.strip()
            st.rerun()
        else:
            st.error("Key không hợp lệ — phải bắt đầu bằng `nvapi-`. Vui lòng kiểm tra lại.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


require_api_key()


# ════════════════════════════════════════════════════════════════════════════════
#  ĐỊNH NGHĨA GRAPH TĨNH CHO MỖI LUỒNG
# ════════════════════════════════════════════════════════════════════════════════

LG_NODES = [
    ("__start__", "START", "oval"),
    ("classify_node", "classify_node\n(phân loại ý định)", "box"),
    ("qna_node", "qna_node\n(hỏi đáp catalog · text-to-SQL)", "box"),
    ("search_node", "search_node\n(tra cứu hóa đơn · MCP)", "box"),
    ("refund_node", "refund_node\n(hoàn tiền · MCP)", "box"),
    ("__end__", "END", "oval"),
]
LG_EDGES = [
    ("__start__", "classify_node"),
    ("classify_node", "qna_node"),
    ("classify_node", "search_node"),
    ("classify_node", "refund_node"),
    ("qna_node", "__end__"),
    ("search_node", "__end__"),
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
        '  edge [fontname="Segoe UI", fontsize=9, color="#5b6776"];',
    ]
    for nid, label, shape in nodes:
        esc = label.replace("\n", "\\n")
        if nid == current:                       # node đang chạy → cam, viền đậm
            style = 'style="filled,bold", fillcolor="#f59e0b", fontcolor="white", color="#b45309", penwidth=2.5'
        elif nid in active_nodes:                # đã chạy qua → xanh
            style = 'style=filled, fillcolor="#22c55e", fontcolor="white", color="#16a34a"'
        else:                                    # chưa chạy → xám
            style = 'style=filled, fillcolor="#2b3340", fontcolor="#aeb9c7", color="#3a4454"'
        lines.append(f'  "{nid}" [label="{esc}", shape={shape}, {style}];')
    for src, dst in edges:
        if (src, dst) in active_edges:
            lines.append(f'  "{src}" -> "{dst}" [color="#22c55e", penwidth=2.5];')
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
    dot = build_dot(nodes, edges, set(ordered), edges_from_path(ordered))
    placeholder.graphviz_chart(dot, width="stretch")


def static_path(placeholder, ordered, nodes, edges):
    placeholder.graphviz_chart(
        build_dot(nodes, edges, set(ordered), edges_from_path(ordered)),
        width="stretch",
    )


# ════════════════════════════════════════════════════════════════════════════════
#  LUỒNG LANGGRAPH
# ════════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_lg_graph():
    import main as lg  # llm_workflow/main.py
    return lg.build_graph()


def run_langgraph(question, thread_id):
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
    branch = {"qna": "qna_node", "search": "search_node"}.get(intent, "refund_node")
    ordered = ["__start__", "classify_node", branch, "__end__"]
    answer = result.get("answer") or (result["messages"][-1].content if result.get("messages") else "")
    return {
        "status": "answer",
        "ordered": ordered,
        "answer": answer,
        "trace": [f"Ý định được phân loại: **{intent or '?'}** → đi nhánh `{branch}`"],
    }


# ════════════════════════════════════════════════════════════════════════════════
#  LUỒNG NAT (in-process + bắt intermediate steps)
# ════════════════════════════════════════════════════════════════════════════════

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

st.markdown(
    '<div class="hero"><h1>🎵 Music Store Agent — LangGraph vs NeMo Agent Toolkit</h1>'
    '<p>Cùng một bài toán (hỏi đáp catalog + hoàn tiền hóa đơn) — 2 luồng agent, '
    'trực quan hóa đường chạy theo thời gian thực.</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### ⚙️ Cấu hình")
    flow = st.radio("Luồng agent", ["LangGraph", "NeMo Agent Toolkit (NAT)"])
    animate = st.toggle("Animate đường chạy", value=True)

    st.divider()
    st.markdown("**Trạng thái dịch vụ**")
    if mcp_alive():
        st.markdown('<span class="pill ok">🟢 MCP server :%d</span>' % MCP_PORT, unsafe_allow_html=True)
    else:
        st.markdown('<span class="pill bad">🔴 MCP server :%d</span>' % MCP_PORT, unsafe_allow_html=True)
    if _key_valid(os.environ.get("NVIDIA_API_KEY", "")):
        st.markdown('<span class="pill ok">🟢 NVIDIA_API_KEY</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="pill bad">🔴 NVIDIA_API_KEY</span>', unsafe_allow_html=True)

    st.divider()
    if st.button("🔄 Reset dữ liệu demo", width="stretch"):
        ok = reset_db_now()
        st.session_state["history"] = []
        st.session_state["last_run"] = None
        st.session_state["pending"] = None
        st.toast("Đã reset DB về bản gốc." if ok else "Không tìm thấy seed DB.", icon="✅" if ok else "⚠️")
        st.rerun()
    if st.button("🚪 Đổi API key", width="stretch"):
        st.session_state.pop("nvidia_key", None)
        os.environ.pop("NVIDIA_API_KEY", None)
        st.rerun()

    st.divider()
    st.caption(
        "**Gợi ý câu hỏi**\n"
        "- Search invoices for Bjorn Hansen\n"
        "- Find invoices for Helena Holy\n"
        "- Refund invoice 3\n"
        "- What albums does AC/DC have? (LangGraph)"
    )

# state
st.session_state.setdefault("history", [])
st.session_state.setdefault("last_run", None)
st.session_state.setdefault("pending", None)
st.session_state.setdefault("tid", 0)
st.session_state.setdefault("animate_next", False)

col_chat, col_graph = st.columns([0.52, 0.48], gap="large")

# ── Cột graph ───────────────────────────────────────────────────────────────────
with col_graph:
    st.markdown("#### 🗺️ Đường chạy")
    nodes, edges = (LG_NODES, LG_EDGES) if flow == "LangGraph" else (NAT_NODES, NAT_EDGES)
    graph_ph = st.empty()
    lr = st.session_state["last_run"]
    if lr and lr["flow"] == flow:
        static_path(graph_ph, lr["ordered"], nodes, edges)
    else:
        graph_ph.graphviz_chart(build_dot(nodes, edges, set(), set()), width="stretch")
    st.markdown('<span class="legend">🟠 đang chạy · 🟢 đã qua · ⚪ chưa chạy</span>', unsafe_allow_html=True)

# ── Cột chat ────────────────────────────────────────────────────────────────────
with col_chat:
    st.markdown(f"#### 💬 Chat — {flow}")

    for m in st.session_state["history"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Xử lý interrupt (LangGraph, intent unknown)
    if st.session_state["pending"]:
        p = st.session_state["pending"]
        st.info(p["prompt"])
        choice = st.radio("Chọn nhánh:", ["qna", "search", "refund"], horizontal=True, key="resume_choice")
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
