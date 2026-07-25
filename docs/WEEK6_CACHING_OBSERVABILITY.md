# Week 6 operations: Redis caching and Langfuse observability

## Data flow

```text
RAG request
  -> start Langfuse root trace
  -> exact cache lookup
     -> hit: return cached answer / replay SSE
     -> miss: hybrid retrieval -> prompt -> Ollama
  -> cache only complete successful response
  -> return cache_hit and trace_id
  -> optional user feedback score
```

## Cache contract

The key is a SHA-256 digest of every request field that can change the answer:

```text
response schema version
normalized query
resolved Ollama model
top_k
use_hybrid
sorted unique categories
```

The cache payload deliberately excludes trace IDs. Every request receives a new trace, including cache hits.

Default TTL is 86,400 seconds. Change it with:

```dotenv
PAPERFORGE_RAG_CACHE__TTL_SECONDS=86400
```

## Privacy defaults

`PAPERFORGE_LANGFUSE__CAPTURE_CONTENT=false` is the safe default. In that mode, trace inputs and outputs contain character counts and short SHA-256 fingerprints, not raw user questions, prompts, or answers. Enable raw content only for a controlled local demo.

## Startup

Generate secrets inside the Linux application container:

```bash
make observability-secrets
```

Copy the output to `.env`, replace all placeholders, then run:

```bash
make up-week6
make observability-health
make readiness
```

Langfuse UI is available at `http://localhost:3000`.

## Smoke test

```bash
make rag-ask Q="What is RAG?"
make cache-stats
make rag-ask Q="What is RAG?"
make cache-stats
```

The first answer should report `cache_hit=false`; the second should report `cache_hit=true`. `hits`, `misses`, and `writes` should increase accordingly.

## Exact invalidation

```bash
make cache-invalidate Q="What is RAG?" TOP_K=3 HYBRID=true
```

The invalidation request must use the same model, top-k, mode, and category set as the original request.

## Feedback

Read `trace_id` from `/ask` or the SSE metadata event, then run:

```bash
make feedback TRACE_ID=<32-hex-trace-id> VALUE=1 COMMENT="Grounded and useful"
```

Use `VALUE=0` for negative feedback.

## Failure behavior

| Failure | Expected behavior |
|---|---|
| Application Redis unavailable | RAG still runs; cache metrics record errors where possible |
| Langfuse unavailable and optional | RAG still runs; readiness becomes degraded |
| Langfuse disabled | `trace_id` is null; feedback returns HTTP 503 |
| Ollama unavailable | Existing Week 5 HTTP 503 behavior remains |
| Stream interrupted | Partial answer is not cached |

## Resource guidance for Intel Mac

The Langfuse stack adds web, worker, Postgres, ClickHouse, Redis, and MinIO. Start it only when testing observability. The core RAG stack remains usable with Langfuse disabled.

## Shutdown

Preserve data:

```bash
make down
```

Delete all application and observability volumes only when intentionally resetting the project:

```bash
make reset
```
