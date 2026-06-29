FROM python:3.11-slim

WORKDIR /app

# Memket agent + dependencies
COPY .skills/memket/lib/ /app/lib/
COPY .skills/memket/scripts/ /app/scripts/

# Persistent store path (mounted via fly volume or emptyDir)
RUN mkdir -p /data
ENV MEMKET_STORE_PATH=/data/store.db

RUN pip install --no-cache-dir fastapi uvicorn requests web3 eth-account hexbytes

ENV PORT=8000
ENV MEMKET_AGENT_NAME=memket-agent
ENV MEMKET_AGENT_ADDRESS=0x0000000000000000000000000000000000000000

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
PYTHONPATH=/app/lib
