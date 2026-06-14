# mcp-server-invoice-test — Minimal test cases cho Invoice MCP Server

Kiểm tra **`mcp-servers/invoice/src/mcp_server_invoice/server_http.py`** theo yêu cầu Assignment 1.

## Chạy

```bash
# từ thư mục gốc dự án
python mcp-server-invoice-test/test_invoice_server.py
# hoặc
pytest mcp-server-invoice-test/test_invoice_server.py -v
```

Test **tự khởi động MCP server** nếu chưa chạy. Exit code `0` = tất cả PASS.
Phần refund (ghi DB) được **backup → test → restore** nên không làm hỏng dữ liệu demo.

## Test verify những gì

### Static — Module 03 pattern
| Kiểm tra |
|---|
| `Server("invoice")` |
| `@server.list_tools()` |
| `@server.call_tool()` |
| `Starlette(...)` + `uvicorn` |

### Live — gọi tool qua MCP (`InvoiceMCPClient`)
| Tool | Test case | Kỳ vọng |
|---|---|---|
| (list) | `tools/list` | có cả `invoice_search` và `invoice_refund` |
| `invoice_search` | theo tên khách (`Helena Holy`) | trả `Invoice #…` + invoice line (track/artist/giá) |
| `invoice_search` | theo **số điện thoại** một phần (`420 2 4177`) | tìm ra Helena Holy |
| `invoice_search` | lọc **artist** (`Beatles`) | giữ Beatles, loại Metallica |
| `invoice_search` | khách không tồn tại | `No customer found …` |
| `invoice_search` | khách có hóa đơn đã refund (`Bjorn Hansen`) | hiện nhãn `[REFUNDED]` |
| `invoice_refund` | id không tồn tại (`9999`) | `Error …` (TextContent) |
| `invoice_refund` | hóa đơn đã refund (`#2`) | `… already been refunded …` |
| `invoice_refund` | hóa đơn còn hiệu lực (`#3`) | `Refund successful … $1.98`, rồi trạng thái đổi |

> Các tool trả kết quả dạng `TextContent` đúng theo yêu cầu Assignment 1
> (`invoice_search` trả invoice lines lọc theo customer + artist/track;
> `invoice_refund` cập nhật trạng thái và trả success/error).

## Liên quan
- Server: `mcp-servers/invoice/src/mcp_server_invoice/server_http.py`
- Client dùng để gọi: `llm_workflow/mcp_http_client.py`
- Dữ liệu: `mcp-servers/invoice/data/chinook.db` (xem `DATABASE.md`)
