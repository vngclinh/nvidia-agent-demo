# qna-agent-test — Verify QNA Agent Skill

Kiểm tra **SKILL.md** (`qna_agent/skills/music-store-assistant/SKILL.md`) được **nạp và tiêu thụ
đúng** bởi `qna_node` (LangGraph) — theo yêu cầu Assignment 2.

## Chạy

```bash
# từ thư mục gốc dự án
python qna-agent-test/test_skill.py
# hoặc
pytest qna-agent-test/test_skill.py -v
```

Exit code `0` = tất cả PASS. (Live check tự **bỏ qua** nếu chưa có `NVIDIA_API_KEY` trong `.env`.)

## Test verify những gì

### Static (không cần API key)
| Kiểm tra | Tiêu chí Assignment |
|---|---|
| Front-matter có `name` + `description`, `name = music-store-assistant` | YAML front-matter |
| Description cụ thể (nhắc album/track) và nêu loại trừ (invoice/refund) | "be specific" |
| Body có schema `Artist`/`Album`/`Track` + mục **SQL Conventions** + ví dụ SELECT | mô tả schema + conventions |
| Ước lượng token ≤ **5000** | progressive-disclosure budget |
| `_is_safe_select` cho SELECT/WITH, chặn DELETE/UPDATE/DROP/multi-statement | read-only an toàn |
| Kết nối read-only chặn ghi ở tầng SQLite (`mode=ro`) | defense in depth |

### Live (cần `NVIDIA_API_KEY`)
End-to-end qua graph với câu hỏi *"What albums does AC/DC have?"*:

- Phân loại đúng `intent = qna`.
- `qna_node` **sinh SQL → thực thi thật** → trả về đúng **2 album trong DB**
  (*Back in Black*, *Highway to Hell*).
- **Không bịa** các album AC/DC ngoài đời nhưng không có trong DB
  (*For Those About To Rock*, *Let There Be Rock*, *Stiff Upper Lip*, *Who Made Who*).

> Đây chính là hồi quy cho lỗi hallucination trước đây: khi `qna_node` chỉ "giả lập" truy vấn bằng
> keyword search, LLM bịa ra discography thật của AC/DC. Sau khi chuyển sang **text-to-SQL thật**
> (LLM sinh SQL → app chạy SELECT read-only → LLM diễn giải từ kết quả), câu trả lời bám đúng DB.

## Liên quan

- Skill: `qna_agent/skills/music-store-assistant/SKILL.md`
- Node tiêu thụ skill: `qna_node` trong `llm_workflow/main.py`
- Dữ liệu: `mcp-servers/invoice/data/chinook.db` (xem `DATABASE.md`)
