# syntax=docker/dockerfile:1.6
#
# HF Space "keep-alive" worker. Single Python process, no compiler chain.
FROM python:3.12-slim

# httpx pulls in anyio + sniffio + certifi; keep image minimal.
RUN pip install --no-cache-dir "httpx>=0.27,<1.0"

WORKDIR /app
COPY app.py ./

# HF Spaces send traffic to $PORT (defaults to 7860). The HTTP server in
# app.py listens on this port so external pings (the "A" leg) get a
# successful 200 back.
EXPOSE 7860
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "app.py"]
