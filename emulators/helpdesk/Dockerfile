ARG VENA_PYTHON_IMAGE=python:3.12-slim
FROM ${VENA_PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/emulator
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10002 --create-home emulator && install -d -o emulator /srv/emulator/state
COPY emulator.py ./
COPY fixtures ./fixtures
USER 10002
EXPOSE 8090
CMD ["uvicorn", "emulator:app", "--host", "0.0.0.0", "--port", "8090"]
