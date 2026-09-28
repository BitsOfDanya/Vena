FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/ml
COPY infra/docker/ml-requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY ml/pipeline ./pipeline
COPY ml/artifacts ./artifacts
COPY ml/configs ./configs
COPY ml/score_snapshot.py ml/stream_scoring.py ./
# The API (uid 10001) writes event batches into this shared volume.
RUN mkdir -p /srv/ml/inbox && chown 10001:10001 /srv/ml/inbox
COPY infra/scripts/ml-worker.py ./worker.py
CMD ["python", "worker.py"]
