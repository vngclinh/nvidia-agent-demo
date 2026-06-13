# Music Store Agent — Demo NVIDIA (LangGraph + NeMo Agent Toolkit + MCP)

Demo một **agent cửa hàng nhạc** dùng database [Chinook](https://github.com/lerocha/chinook-database).
Cùng một bài toán (hỏi đáp catalog + hoàn tiền hóa đơn) được triển khai bằng **2 luồng độc lập**:

| Luồng | File | Phong cách |
|-------|------|-----------|
| **LangGraph** | `llm_workflow/main.py` | Code Python tường minh, có rẽ nhánh + human-in-the-loop |
| **NeMo Agent Toolkit (NAT)** | `nemo_agent_toolkit/workflow.yaml` | Khai báo (declarative) bằng YAML, agent kiểu ReAct |

Cả hai dùng chung:
- **LLM:** `meta/llama-3.3-70b-instruct` qua NVIDIA NIM (cloud, cần API key)
- **Dữ liệu/tool:** một **MCP server** (`mcp-servers/invoice/...`) phục vụ DB Chinook

---

## 1. Kiến trúc

```
                BẠN (terminal / trình duyệt)
                       │
        ┌──────────────┴───────────────┐
        ▼                              ▼
┌─────────────────┐          ┌─────────────────────┐
│  LangGraph      │          │  NAT server (8000)  │   ← agent
│  main.py (CLI)  │          │  nat serve          │
└────────┬────────┘          └──────────┬──────────┘
         │  (nhánh refund)              │ gọi tool qua MCP
         │  ───────────────┐            │
         ▼                 ▼            ▼
   sqlite trực tiếp   ┌────────────────────────────┐
   (nhánh qna)        │  MCP server (port 8765)    │   ← kho tool + dữ liệu
                      │  server_http.py            │
                      │  tool: invoice_search,     │
                      │        invoice_refund      │
                      └────────────┬───────────────┘
                                   ▼
                            chinook.db (SQLite)
```

> **Vì sao 2 server?** MCP server (8765) chỉ *cung cấp công cụ* (chạy SQL trên DB), không biết
> nói chuyện. NAT server (8000) là *bộ não* (gọi LLM, suy luận, quyết định gọi tool nào) nhưng
> không tự biết dữ liệu. Hai bên bổ trợ nhau — đây chính là mô hình MCP: tách agent khỏi tool/dữ liệu.

---

## 2. Cài đặt (làm 1 lần)

```powershell
# 1. Tạo & kích hoạt virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Cài thư viện
pip install -r requirements.txt
```

### Tạo file `.env`

Ở thư mục gốc, tạo `.env` (đã có sẵn `.gitignore` chặn commit). Lấy API key **miễn phí**
tại <https://build.nvidia.com>:

```dotenv
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxx
MCP_PORT=8765
```

Cả `main.py`, `server_http.py` và script `run_nat.ps1` đều **tự đọc `.env`** — không cần gõ key
vào terminal nữa.

---

## 3. Chạy

### Bước chung: bật MCP server (BẮT BUỘC, giữ chạy liên tục)

> Cả 2 luồng đều cần tool từ MCP server. Mở **Terminal 1** và để yên:

```powershell
.\.venv\Scripts\Activate.ps1
python mcp-servers\invoice\src\mcp_server_invoice\server_http.py
```
Thấy `Application startup complete` là OK (lắng nghe ở `http://127.0.0.1:8765/mcp/`).

> ⚠️ Lỗi `[Errno 10048] ... bind on 8765` = đã có server khác chiếm port. Kiểm tra:
> `Get-NetTCPConnection -LocalPort 8765 -State Listen` rồi `Stop-Process -Id <PID> -Force`.

---

### Luồng A — LangGraph (CLI chat)

**Terminal 2:**
```powershell
.\.venv\Scripts\Activate.ps1
python llm_workflow\main.py
```
Chat trực tiếp trong terminal. Thử:
- `What albums does AC/DC have?` → nhánh **qna**
- `I want to refund invoice for Leonie Kohler` → nhánh **refund**

### Luồng B — NeMo Agent Toolkit (NAT)

Dùng script `run_nat.ps1` (tự nạp `.env`). Có 2 chế độ:

**B1. Chạy 1 lần, in kết quả ra màn hình (`run`):**
```powershell
.\run_nat.ps1 run --config_file nemo_agent_toolkit\workflow.yaml --input "Search invoices for Bjorn Hansen"
```

**B2. Chạy như web API (`serve`):**
```powershell
.\run_nat.ps1 serve --config_file nemo_agent_toolkit\workflow.yaml
```
Server mở ở `http://localhost:8000`. Gửi câu hỏi vào (xem mục 5).

---

## 4. Chi tiết 2 luồng

### Luồng A — LangGraph (`llm_workflow/main.py`)

Graph có **rẽ nhánh theo ý định** + **human-in-the-loop**:

```
START → classify_node → route ┬─ "qna"    → qna_node    → END
                              ├─ "refund" → refund_node → END
                              └─ "unknown"→ interrupt() → hỏi lại user → resume
```

- **`classify_node`** — LLM phân loại câu hỏi thành `qna` / `refund` / `unknown`.
  Nếu `unknown` → `interrupt()` tạm dừng graph, hỏi người dùng chọn nhánh (cần `InMemorySaver`).
- **`qna_node`** — đọc `qna_agent/.../SKILL.md` (hướng dẫn + schema DB) rồi **query Chinook trực
  tiếp bằng `sqlite3`** (KHÔNG qua MCP), đưa kết quả + skill vào prompt cho LLM trả lời.
- **`refund_node`** — gọi **MCP server**: `invoice_search` tìm hóa đơn, nếu đúng 1 hóa đơn thì tự
  `invoice_refund` (xóa invoice line, set total = 0).

> Đặc điểm: kiểm soát luồng chi tiết, dễ chèn logic, có trạng thái hội thoại.

### Luồng B — NeMo Agent Toolkit (`nemo_agent_toolkit/workflow.yaml`)

Mô tả agent bằng YAML thay vì code:
```yaml
function_groups:
  mcp_invoice:           # tự nạp tool từ MCP server (8765)
    _type: mcp_client
llms:
  nim_llm:               # LLM meta/llama-3.3-70b qua NIM
    _type: nim
workflow:
  _type: react_agent     # agent kiểu ReAct: Thought → Action → Observation → Final Answer
  tool_names: [mcp_invoice]
  llm_name: nim_llm
```

- Agent **tự động** khám phá tool từ MCP server, tự quyết định gọi `invoice_search`/`invoice_refund`.
- Vòng suy luận ReAct hiện trong log: `Thought` → `Action` → `Tool's response` → `Final Answer`.

> Đặc điểm: ít code, cấu hình thuần khai báo, dễ đổi model/tool, có sẵn `serve` thành REST API.

**So sánh nhanh:**

| | LangGraph | NAT |
|---|---|---|
| Cách định nghĩa | Code Python | YAML |
| Điều khiển luồng | Tường minh (node/edge) | Agent tự suy luận (ReAct) |
| Rẽ nhánh / human-in-loop | Có (`interrupt`) | Không (mặc định) |
| Truy cập DB | qna: sqlite trực tiếp; refund: MCP | Luôn qua MCP |
| Triển khai API | Tự viết | `nat serve` sẵn |

---

## 5. Gửi câu hỏi vào NAT server (`serve`)

NAT server (8000) là API **chờ request** — bạn phải gửi câu hỏi vào. 3 cách:

**Cách 1 — Trình duyệt (dễ nhất):** mở <http://localhost:8000/docs> → `POST /generate` →
*Try it out* → gõ vào `input_message` → *Execute*.

**Cách 2 — PowerShell:**
```powershell
$body = @{ input_message = "Search invoices for Bjorn Hansen" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/generate -Method Post -ContentType "application/json" -Body $body
```

**Cách 3 — curl** (ghi JSON ra file để tránh PowerShell làm hỏng dấu nháy):
```powershell
'{"input_message":"Search invoices for Bjorn Hansen"}' | Out-File $env:TEMP\b.json -Encoding ascii -NoNewline
curl.exe -X POST http://localhost:8000/generate -H "Content-Type: application/json" --data-binary "@$env:TEMP\b.json"
```

Kết quả mẫu:
```json
{"value":"Invoice #2 for Bjorn Hansen contains 10 tracks and has a total of $9.90."}
```

| Endpoint | Công dụng |
|----------|-----------|
| `POST /generate` | Hỏi 1 lần, nhận 1 trả lời |
| `POST /generate/stream` | Trả lời dạng streaming |
| `GET /health` | Kiểm tra server sống |
| `GET /docs` | Giao diện web thử nghiệm |

---

## 6. Câu hỏi mẫu

- `Search invoices for Bjorn Hansen` — khách còn dữ liệu nguyên
- `Find invoices for Helena Holy`
- `Refund invoice 3` — thử nhánh hoàn tiền (agent gọi `invoice_refund`)
- `What albums does AC/DC have?` — (chỉ luồng LangGraph, nhánh qna)

> Lưu ý: refund **sửa DB thật** (xóa invoice line, set total = 0). Hóa đơn #1 (Leonie Kohler) đã
> bị refund trong các lần demo trước nên trả về rỗng.

---

## 7. Demo bằng Streamlit (`app.py`) — có visualize đường chạy

File **`app.py`** là một giao diện web: chọn 1 trong 2 luồng (LangGraph / NAT), chat, và
**vẽ graph các node + tô màu dần theo đường chạy thực tế** (🟠 đang chạy · 🟢 đã qua · ⚪ chưa chạy).

**Chạy:**
```powershell
# Terminal 1 — MCP server (bắt buộc, cả 2 luồng đều cần)
python mcp-servers\invoice\src\mcp_server_invoice\server_http.py

# Terminal 2 — Streamlit
streamlit run app.py
```
Mở trình duyệt vào địa chỉ Streamlit in ra (mặc định <http://localhost:8501>).

**Cách hoạt động:**
- **LangGraph**: chạy graph *in-process* (import `build_graph()`), suy ra đường chạy từ `intent`
  (`__start__ → classify_node → qna_node|refund_node → __end__`). Nếu ý định `unknown`, app hiện
  ô chọn nhánh (đúng cơ chế `interrupt()` human-in-the-loop).
- **NAT**: chạy workflow *in-process* qua `load_workflow()` và **bắt intermediate steps** để biết
  agent gọi tool nào → vẽ `START → agent → invoice_search/refund → agent → END`.
  (App này gọi NAT trực tiếp, **không cần** `nat serve`.)

> Lưu ý: app cần MCP server (8765) chạy + `NVIDIA_API_KEY` trong `.env`. Thanh bên trái hiển thị
> trạng thái 🟢/🔴 của hai thứ này.

**Khi deploy (Streamlit Community Cloud…):** đặt `NVIDIA_API_KEY` qua **Secrets**, và lưu ý MCP
server phải chạy ở nơi app truy cập được (cùng máy/cùng mạng) — đây là điểm khó nhất khi deploy
public, vì cần host thêm tiến trình MCP server.

---

## 8. Cấu trúc thư mục

```
demo_nvidia/
├── .env                    # API key + cấu hình (KHÔNG commit)
├── README.md
├── requirements.txt
├── app.py                  # UI Streamlit (chọn luồng + visualize đường chạy)
├── run_nat.ps1             # wrapper: nạp .env rồi chạy nat
├── llm_workflow/
│   ├── main.py             # Luồng A — LangGraph CLI
│   └── mcp_http_client.py  # client gọi MCP server
├── mcp-servers/invoice/
│   ├── src/mcp_server_invoice/server_http.py   # MCP server (tool)
│   └── data/chinook.db     # database
├── qna_agent/skills/music-store-assistant/SKILL.md  # hướng dẫn nhánh qna
└── nemo_agent_toolkit/
    └── workflow.yaml       # Luồng B — cấu hình NAT
```

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân & cách sửa |
|-------------|------------------------|
| `[Errno 10048] bind on 8765` | Đã có MCP server chạy. Dùng cái đó, hoặc `Stop-Process -Id <PID>`. |
| NAT lỗi `Failed to initialize component mcp_invoice` | Chưa bật MCP server (8765). Bật trước rồi chạy lại NAT. |
| `[401] Unauthorized` | `NVIDIA_API_KEY` sai/thiếu/đã thu hồi. Kiểm tra `.env`, tạo key mới. |
| `serve` chạy nhưng "không thấy kết quả" | Đúng — `serve` là API chờ request. Gửi câu hỏi (mục 5). |
| `nat: command not found` | Chưa `pip install nvidia-nat nvidia-nat-langchain nvidia-nat-mcp` trong venv. |
```
