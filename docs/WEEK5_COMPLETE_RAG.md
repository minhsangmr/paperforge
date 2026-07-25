# Week 5 Complete RAG Operations

## Services

Week 5 adds two Compose profiles:

- `llm`: Ollama and one-shot model initialization;
- `app-ui`: Gradio connected to the internal FastAPI URL.

The default local model is `llama3.2:1b`, selected because it is practical for CPU-only development. A larger model may be configured, but model size and latency increase materially on an Intel Mac running Docker Desktop.

## Configuration

Copy missing values from `.env.example` into the ignored `.env` file. The important settings are:

```dotenv
PAPERFORGE_OLLAMA__ENABLED=true
PAPERFORGE_OLLAMA__URL=http://ollama:11434
PAPERFORGE_OLLAMA__DEFAULT_MODEL=llama3.2:1b
PAPERFORGE_OLLAMA__REQUEST_TIMEOUT_SECONDS=120
PAPERFORGE_RAG__DEFAULT_TOP_K=3
PAPERFORGE_RAG__MAX_CONTEXT_CHARACTERS=24000
PAPERFORGE_RAG__MAX_ANSWER_WORDS=300
PAPERFORGE_UI__API_BASE_URL=http://api:8000/api/v1
```

The Ollama and RAG default model values should be kept equal.

## Dependency synchronization

```bash
make build
make lock
make sync
make sync-ui
```

`uv.lock` must be generated inside Linux because Week 5 adds the optional Gradio dependency group.

## Start Ollama separately first

```bash
make up-llm
make ollama-pull
make ollama-models
```

The model remains in `paperforge_ollama` across container recreation.

## Start the full stack

```bash
make up-week5
make ps
make readiness
```

If no Jina key is configured, use text-only hybrid indexing or allow RAG retrieval to fall back to chunk BM25:

```bash
make hybrid-index-text
make rag-ask Q="What do the papers say about retrieval?" HYBRID=true
```

## Complete response

```bash
make rag-ask Q="What is retrieval-augmented generation?" TOP_K=3 HYBRID=true
```

Equivalent API request:

```bash
curl -X POST http://localhost:8000/api/v1/ask   -H 'Content-Type: application/json'   -d '{
    "query": "What is retrieval-augmented generation?",
    "top_k": 3,
    "use_hybrid": true,
    "model": "llama3.2:1b",
    "categories": ["cs.AI", "cs.IR"]
  }'
```

The response includes the exact chunk sources used, search mode, model, and normalized Ollama token/latency metadata.

## Streaming response

```bash
make rag-stream Q="Explain attention using the indexed papers"
```

SSE event order:

```text
event: metadata
event: token
event: token
...
event: done
```

Expected headers include `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and `X-Accel-Buffering: no`.

## Gradio

```bash
make up-ui
```

Open `http://localhost:7861`. The browser connects to Gradio, and the Gradio container calls `http://api:8000/api/v1/stream`; it never assumes that `localhost:8000` means the API from inside another container.

## Failure checks

Stop Ollama:

```bash
docker compose --profile llm stop ollama
make rag-ask Q="What is RAG?"
```

The API should return HTTP 503 while liveness remains HTTP 200. Restart and confirm the persistent model:

```bash
make up-llm
make ollama-models
```

## Tests

```bash
make compose-config
make check
make test-component
```

Unit tests mock Ollama and embeddings. CI must not pull a model or require a Jina key. The real model and SSE smoke tests are local acceptance gates.

## Resource guidance for Mac Intel

Start only the profiles needed for the current task. Stop Airflow and OpenSearch Dashboards before running generation if Docker Desktop memory is constrained. Use `llama3.2:1b`, `top_k=1` or `top_k=3`, and a 512-token output limit for the fastest CPU feedback loop.
