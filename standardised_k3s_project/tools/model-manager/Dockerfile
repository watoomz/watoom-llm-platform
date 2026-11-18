FROM python:3.13-slim@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024
WORKDIR /app/model-manager
COPY image_mcp.py image_publish.py admission_errors.py server.py hf.py settings.py store.py worker.py operations.py download.py file_lock.py broker_service.py broker.py workload.py gguf_header.py ./
COPY web ./web
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1009:1009
ENTRYPOINT ["python3","/app/model-manager/server.py"]
