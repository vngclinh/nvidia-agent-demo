---
title: Music Store Agent
emoji: 🎵
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: LangGraph vs NeMo Agent Toolkit + MCP demo
---

# 🎵 Music Store Agent — LangGraph vs NeMo Agent Toolkit

Demo một **agent cửa hàng nhạc** (database [Chinook](https://github.com/lerocha/chinook-database))
giải cùng một bài toán — **hỏi đáp catalog** + **hoàn tiền hóa đơn** — bằng **2 luồng độc lập**,
và **trực quan hóa đường chạy** qua các node theo thời gian thực.

| Luồng | Phong cách |
|-------|-----------|
| **LangGraph** | Code Python tường minh, rẽ nhánh + human-in-the-loop |
| **NeMo Agent Toolkit (NAT)** | Khai báo bằng YAML, agent kiểu ReAct |

## 🔑 Cần API key (miễn phí)

Khi mở app, bạn sẽ được yêu cầu nhập **NVIDIA API key**:

1. Mở <https://build.nvidia.com/meta/llama-3_3-70b-instruct>
2. Đăng nhập → **Get API Key**
3. Dán key dạng `nvapi-...` vào ô trong app.

Key chỉ lưu trong phiên trình duyệt của bạn (không ghi ra đĩa, không chia sẻ).

## ℹ️ Ghi chú

- App **tự khởi động MCP server** nội bộ — không cần cấu hình thêm.
- **Dữ liệu demo tự reset** về bản gốc mỗi khi Space khởi động, nên thao tác hoàn tiền (ghi vào DB)
  không làm hao dữ liệu lâu dài. Có nút **🔄 Reset dữ liệu demo** trong thanh bên.

## 💬 Câu hỏi mẫu

- `Search invoices for Bjorn Hansen` — hóa đơn đã hoàn tiền
- `Find invoices for Helena Holy` — hóa đơn còn hiệu lực
- `Refund invoice 3` — hoàn tiền theo số hóa đơn
- `What albums does AC/DC have?` — nhánh hỏi đáp (LangGraph)
