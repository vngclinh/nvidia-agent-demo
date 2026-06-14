# Hugging Face Space (Docker SDK) — chạy Streamlit + MCP server (app tự spawn)
FROM python:3.11-slim

# user không phải root (HF chạy uid 1000) → /app ghi được (cần cho reset DB)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    MCP_PORT=8765

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true"]
