FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY antigravity.py .
COPY codex.py .

RUN pip install uv

RUN uv pip install --system \
    psutil \
    requests \
    urllib3 \
    python-dateutil \
    pytz

EXPOSE 5000
EXPOSE 5001

CMD ["python", "antigravity.py"]