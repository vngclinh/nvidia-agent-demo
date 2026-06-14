"""
Deploy demo lên Hugging Face Spaces (SDK = streamlit).

Dùng:
    HF_TOKEN=hf_xxx HF_SPACE=username/music-store-agent python deploy_hf.py
    # thêm DRY_RUN=1 để chỉ liệt kê file sẽ upload, KHÔNG đẩy lên.

Yêu cầu: pip install huggingface_hub
"""

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi, create_repo

ROOT = Path(__file__).parent

# File/thư mục KHÔNG đẩy lên Space (nhạy cảm / nặng / chỉ dùng local).
IGNORE = [
    ".venv/**", ".git/**", "**/__pycache__/**", "*.pyc",
    ".env", ".env.example",            # tuyệt đối không đẩy key
    "README.md", "README_HF.md",       # README.md trên Space lấy từ README_HF.md
    "deploy_hf.py", "run_nat.ps1",     # script chỉ dùng local
    ".gitignore",
]


def list_files() -> list[str]:
    import fnmatch
    files = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat.rstrip("/*"))
               or rel.startswith(pat.split("/")[0] + "/") and pat.endswith("/**")
               for pat in IGNORE):
            continue
        files.append(rel)
    return sorted(files)


def main():
    dry = os.environ.get("DRY_RUN") == "1"
    space = os.environ.get("HF_SPACE")
    token = os.environ.get("HF_TOKEN")

    print("== Files sẽ upload lên Space ==")
    for f in list_files():
        print("  ", f)

    if dry:
        print("\n[DRY_RUN] Không đẩy lên. Bỏ DRY_RUN để deploy thật.")
        return

    if not space or not token:
        sys.exit("Thiếu HF_SPACE hoặc HF_TOKEN trong môi trường.")

    api = HfApi(token=token)
    print(f"\n== Tạo/đảm bảo Space: {space} (sdk=docker) ==")
    create_repo(space, repo_type="space", space_sdk="docker",
                exist_ok=True, token=token)

    print("== Upload toàn bộ thư mục ==")
    api.upload_folder(
        repo_id=space,
        repo_type="space",
        folder_path=str(ROOT),
        ignore_patterns=IGNORE,
        commit_message="Deploy Music Store Agent demo",
    )

    print("== Đặt README.md (frontmatter HF) từ README_HF.md ==")
    api.upload_file(
        path_or_fileobj=str(ROOT / "README_HF.md"),
        path_in_repo="README.md",
        repo_id=space,
        repo_type="space",
        commit_message="Add Space README/frontmatter",
    )

    print(f"\n✅ Xong! Mở: https://huggingface.co/spaces/{space}")


if __name__ == "__main__":
    main()
