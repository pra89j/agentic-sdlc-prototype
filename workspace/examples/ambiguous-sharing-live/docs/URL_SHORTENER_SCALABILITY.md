# Optional URL Shortener Scale-out Considerations

The generated app is a zero-setup SQLite reference implementation. The following notes are optional future evolution, not requirements for this runnable demo.

## Target architecture

- Run stateless FastAPI instances behind a load balancer; externalize configuration and secrets.
- Store authoritative URL mappings and uniqueness constraints in PostgreSQL. Generate random Base62 codes and let a unique index arbitrate collisions; retry only on unique-key conflicts.
- Use Redis as a cache-aside read-through layer for redirects, with bounded TTL and explicit invalidation on link changes. The database remains authoritative.
- Publish click events asynchronously to a durable queue (for example Kafka or Azure Event Hubs). A consumer deduplicates by event ID and aggregates counts into a separate analytics store. Redirect latency must not wait on analytics aggregation.
- Apply rate limits, request timeouts, health/readiness probes, structured logs, tracing, and metrics for cache hit rate, redirect latency, queue lag, and database saturation.

## Consistency and failure behavior

The redirect lookup is strongly backed by the mapping store on cache miss. Analytics are eventually consistent; queue outages must be visible through lag/alerts and handled with bounded retries or a durable outbox. Define event retention and privacy policy before launch. Avoid silently dropping events or making a failed analytics write turn a valid redirect into an error.

## Capacity and validation gates

Benchmark read/write mix, p95/p99 redirect latency, cache hit rate, database connection limits, and queue throughput using representative load. Exercise cache eviction, database failover, queue backpressure, duplicate events, and recovery. No production load or failover test is claimed by this local prototype.

## Migration path

Keep API contracts stable; introduce a storage interface, migrate SQLite rows to PostgreSQL, dual-read/verify before cutover, then add Redis and asynchronous click ingestion behind feature flags. The runnable demo currently performs synchronous SQLite click increments.