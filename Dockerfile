FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for LSP and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8765

CMD ["python", "-c", "print('IDE Engine container ready. Start the WebSocket server or agent with the configured entrypoint.')"]
