"""
Assignment 1 — Minimal test cases cho Invoice MCP Server.

Kiểm tra server expose đúng 2 tool và chúng hoạt động đúng:
  • invoice_search — lọc theo tên/điện thoại khách + (tùy chọn) artist/track, trả invoice lines.
  • invoice_refund — cập nhật trạng thái hóa đơn, trả success/error dạng TextContent.

Chạy (từ thư mục gốc dự án):
    python mcp-server-invoice-test/test_invoice_server.py
    # hoặc:  pytest mcp-server-invoice-test/test_invoice_server.py -v

Test tự khởi động MCP server nếu chưa chạy. Trường hợp refund (ghi DB) được
backup → test → restore nên KHÔNG làm hỏng dữ liệu demo.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "llm_workflow"))

MCP_PORT = 8765
MCP_URL = f"http://127.0.0.1:{MCP_PORT}/mcp/"
SERVER = ROOT / "mcp-servers" / "invoice" / "src" / "mcp_server_invoice" / "server_http.py"
SRC = SERVER.read_text(encoding="utf-8")
DB = ROOT / "mcp-servers" / "invoice" / "data" / "chinook.db"

_results: list[tuple[bool, str]] = []


def check(cond, label):
    _results.append((bool(cond), label))
    print(("  ✅ " if cond else "  ❌ ") + label)
    return cond


def _alive():
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


def _ensure_server():
    if _alive():
        return None
    print("  …MCP server chưa chạy, đang khởi động.")
    proc = subprocess.Popen([sys.executable, str(SERVER)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(ROOT))
    for _ in range(30):
        if _alive():
            return proc
        time.sleep(0.5)
    raise RuntimeError("Không khởi động được MCP server.")


# ──────────────────────────────────────────────────────────────────────────────
#  STATIC — Module 03 pattern
# ──────────────────────────────────────────────────────────────────────────────

def test_module03_pattern():
    print("\n[Static] Module 03 pattern trong server_http.py")
    check('Server("invoice")' in SRC or "Server('invoice')" in SRC, "Server('invoice')")
    check("@server.list_tools()" in SRC, "@list_tools")
    check("@server.call_tool()" in SRC, "@call_tool")
    check("Starlette(" in SRC and "uvicorn" in SRC.lower(), "Starlette + Uvicorn")
    assert all(ok for ok, _ in _results), "Static pattern check thất bại"


# ──────────────────────────────────────────────────────────────────────────────
#  LIVE — gọi tool qua MCP
# ──────────────────────────────────────────────────────────────────────────────

def test_tools_exposed():
    print("\n[Live] Server expose ≥ 2 tool")
    from mcp_http_client import InvoiceMCPClient
    names = {t["name"] for t in InvoiceMCPClient().list_tools()}
    check("invoice_search" in names, "Có tool invoice_search")
    check("invoice_refund" in names, "Có tool invoice_refund")
    assert all(ok for ok, _ in _results), "Tool list thất bại"


def test_invoice_search():
    print("\n[Live] invoice_search")
    from mcp_http_client import InvoiceMCPClient
    c = InvoiceMCPClient()

    # theo tên khách → trả invoice line có track + artist
    r = c.invoice_search(customer_query="Helena Holy")
    check("Invoice #" in r, "Tìm theo tên trả về hóa đơn")
    check("by" in r and "$" in r, "Có invoice line (track/artist/giá)")

    # theo số điện thoại (một phần)
    r_phone = c.invoice_search(customer_query="420 2 4177")
    check("Helena Holy" in r_phone, "Tìm theo số điện thoại (một phần)")

    # lọc theo artist/track
    r_filt = c.invoice_search(customer_query="Helena Holy", artist_or_track="Beatles")
    check("Beatles" in r_filt and "Metallica" not in r_filt,
          "Lọc artist 'Beatles' (loại Metallica)")

    # khách không tồn tại
    r_none = c.invoice_search(customer_query="Nguyen Khong Co That")
    check(r_none.startswith("No customer found"), "Khách không tồn tại → 'No customer found'")

    # khách có hóa đơn đã refund → vẫn hiện, có nhãn REFUNDED
    r_ref = c.invoice_search(customer_query="Bjorn Hansen")
    check("REFUNDED" in r_ref, "Hóa đơn đã refund hiện nhãn [REFUNDED]")
    assert all(ok for ok, _ in _results), "invoice_search thất bại"


def test_invoice_refund():
    print("\n[Live] invoice_refund (backup → test → restore)")
    from mcp_http_client import InvoiceMCPClient
    c = InvoiceMCPClient()

    # không tồn tại → error TextContent
    check(c.invoice_refund(9999).lower().startswith("error"),
          "Refund hóa đơn không tồn tại → Error")

    # đã refund trước (invoice #2 = Bjorn Hansen) → báo đã refund, không lỗi
    check("already been refunded" in c.invoice_refund(2).lower(),
          "Refund hóa đơn đã refund → báo 'already refunded'")

    # refund THẬT 1 hóa đơn còn hiệu lực (#3) — backup rồi restore
    backup = DB.with_suffix(".testbak")
    shutil.copy(DB, backup)
    try:
        res = c.invoice_refund(3)
        check("refund successful" in res.lower() and "1.98" in res,
              "Refund hóa đơn #3 → success + đúng số tiền $1.98")
        # xác nhận trạng thái đã đổi
        again = c.invoice_search(customer_query="Francois Tremblay")
        check("REFUNDED" in again or "$0.00" in again, "Sau refund, #3 chuyển trạng thái đã refund")
    finally:
        shutil.copy(backup, DB)   # khôi phục dữ liệu demo
        backup.unlink(missing_ok=True)
        print("  …đã restore chinook.db về trạng thái trước test.")
    assert all(ok for ok, _ in _results), "invoice_refund thất bại"


def _run_all():
    server_proc = _ensure_server()
    failed = False
    try:
        for fn in (test_module03_pattern, test_tools_exposed,
                   test_invoice_search, test_invoice_refund):
            try:
                fn()
            except AssertionError as e:
                print(f"  ⛔ {fn.__name__}: {e}")
                failed = True
    finally:
        if server_proc is not None:
            server_proc.terminate()
    total, passed = len(_results), sum(1 for ok, _ in _results if ok)
    print(f"\n=== {passed}/{total} checks PASS ===")
    return 0 if (passed == total and not failed) else 1


if __name__ == "__main__":
    sys.exit(_run_all())
