"""
Assignment 2 — Verify QNA Agent Skill được nạp & tiêu thụ đúng.

Chạy:
    python qna-agent-test/test_skill.py        # in PASS/FAIL, exit code != 0 nếu lỗi
    pytest qna-agent-test/test_skill.py         # cũng chạy được dưới pytest

- Static checks (KHÔNG cần API key): front-matter, token budget, schema, conventions, an toàn SQL.
- Live checks (CHỈ chạy nếu có NVIDIA_API_KEY): qna_node sinh & THỰC THI SQL, trả dữ liệu thật,
  không bịa.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "qna_agent" / "skills" / "music-store-assistant" / "SKILL.md"
sys.path.insert(0, str(ROOT / "llm_workflow"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

TOKEN_BUDGET = 5000
_results: list[tuple[bool, str]] = []


def check(cond: bool, label: str):
    _results.append((bool(cond), label))
    print(("  ✅ " if cond else "  ❌ ") + label)
    return cond


def _front_matter(text: str) -> dict:
    """Parse YAML front-matter tối giản (name + description) — không cần PyYAML."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.S)
    if not m:
        return {}
    fm, out = m.group(1), {}
    for line in fm.splitlines():
        mm = re.match(r"^(\w+)\s*:\s*(.*)$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip()
    return out


def _est_tokens(text: str) -> int:
    return len(text) // 4  # heuristic ~4 ký tự/token


# ──────────────────────────────────────────────────────────────────────────────
#  STATIC CHECKS (không cần API key)
# ──────────────────────────────────────────────────────────────────────────────

def test_skill_static():
    print("\n[Static] Skill file & nội dung")
    assert SKILL.exists(), "SKILL.md không tồn tại"
    text = SKILL.read_text(encoding="utf-8")

    fm = _front_matter(text)
    check("name" in fm and fm["name"], "Front-matter có 'name'")
    check("description" in fm or text[:400].lower().count("description"),
          "Front-matter có 'description'")
    check(fm.get("name") == "music-store-assistant", "name = music-store-assistant")

    # description nên cụ thể: nhắc tới album/track + loại trừ invoice/refund
    desc_zone = text[: text.find("\n---", 4) + 1] if "\n---" in text[4:] else text[:600]
    check("album" in desc_zone.lower() or "track" in desc_zone.lower(),
          "Description cụ thể (nhắc album/track)")
    check("refund" in desc_zone.lower() or "invoice" in desc_zone.lower(),
          "Description nêu loại trừ (invoice/refund)")

    # body mô tả schema + conventions
    low = text.lower()
    check(all(k in text for k in ("Artist", "Album", "Track")), "Body có schema Artist/Album/Track")
    check("sql conventions" in low or "conventions" in low, "Body có mục SQL Conventions")
    check("select" in low, "Body có ví dụ/đề cập SELECT")

    # token budget
    tk = _est_tokens(text)
    check(tk <= TOKEN_BUDGET, f"Token budget ≤ {TOKEN_BUDGET} (ước lượng {tk})")

    assert all(ok for ok, _ in _results), "Có static check thất bại"


def test_sql_safety():
    print("\n[Static] An toàn SQL (chỉ SELECT, read-only)")
    import main
    check(main._is_safe_select("SELECT * FROM Album"), "Cho phép SELECT")
    check(main._is_safe_select("WITH x AS (SELECT 1) SELECT * FROM x"), "Cho phép WITH…SELECT")
    check(not main._is_safe_select("DELETE FROM Album"), "Chặn DELETE")
    check(not main._is_safe_select("UPDATE Album SET Title='x'"), "Chặn UPDATE")
    check(not main._is_safe_select("SELECT 1; DROP TABLE Album"), "Chặn multi-statement/DROP")
    # read-only connection chặn ghi ở tầng kết nối
    _, _, err = main._run_select("UPDATE Album SET Title='x' WHERE AlbumId=1")
    check(bool(err), "Kết nối read-only chặn ghi (defense in depth)")
    assert all(ok for ok, _ in _results), "Có safety check thất bại"


# ──────────────────────────────────────────────────────────────────────────────
#  LIVE CHECK (cần NVIDIA_API_KEY) — verify skill được tiêu thụ end-to-end
# ──────────────────────────────────────────────────────────────────────────────

def test_qna_consumes_skill_live():
    print("\n[Live] qna_node sinh & thực thi SQL, trả dữ liệu thật")
    if not os.environ.get("NVIDIA_API_KEY", "").startswith("nvapi-"):
        print("  ⏭️  Bỏ qua (không có NVIDIA_API_KEY).")
        return

    import main
    from langchain_core.messages import HumanMessage
    graph = main.build_graph()
    out = graph.invoke(
        {"messages": [HumanMessage(content="What albums does AC/DC have?")], "intent": "", "answer": ""},
        config={"configurable": {"thread_id": "test-acdc"}},
    )
    ans = (out.get("answer") or "").lower()

    check(out.get("intent") == "qna", "Phân loại đúng intent = qna")
    check("back in black" in ans and "highway to hell" in ans,
          "Trả về 2 album THẬT trong DB (Back in Black, Highway to Hell)")
    # các album AC/DC ngoài đời nhưng KHÔNG có trong DB — không được bịa
    for fake in ("for those about to rock", "let there be rock", "stiff upper lip", "who made who"):
        check(fake not in ans, f"Không bịa album '{fake}'")
    assert all(ok for ok, _ in _results), "Live check thất bại"


def _run_all():
    failed = False
    for fn in (test_skill_static, test_sql_safety, test_qna_consumes_skill_live):
        try:
            fn()
        except AssertionError as e:
            print(f"  ⛔ {fn.__name__}: {e}")
            failed = True
    total = len(_results)
    passed = sum(1 for ok, _ in _results if ok)
    print(f"\n=== {passed}/{total} checks PASS ===")
    return 0 if (passed == total and not failed) else 1


if __name__ == "__main__":
    sys.exit(_run_all())
