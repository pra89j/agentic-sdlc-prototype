# Optional URL Shortener Scale-out Considerations

## Scope and status

The generated application is a runnable local demo using SQLite and synchronous click
increments. The following notes are optional future evolution ideas, not requirements for
meeting the assignment and not functionality implemented by the prototype.

## Proposed architecture

```text
Clients
  |
API gateway / load balancer
  |
Stateless FastAPI instances ------ Redis (redirect cache)
  |                                   |
  +---------------- PostgreSQL (authoritative mappings)
  |
  +--> durable click-event queue --> analytics consumers --> OLAP/aggregate store
```

### Mapping and redirect path

- Keep API instances stateless and horizontally scalable.
- Use PostgreSQL as the source of truth with a unique index on the short code.
- Generate cryptographically random Base62 codes; let the unique constraint arbitrate
  collisions and retry only on a uniqueness conflict.
- Cache successful lookups in Redis with a bounded TTL. PostgreSQL remains authoritative;
  define invalidation behavior before adding link update/delete operations.
- Protect create and redirect endpoints with rate limits, request timeouts, and abuse controls.

### Analytics path

- Publish a click event with a unique event ID after resolving a redirect. Do not block the
  redirect response on aggregation.
- Use a durable queue (Kafka or Azure Event Hubs are examples) and consumers that deduplicate
  by event ID before updating aggregates.
- Make analytics eventually consistent and expose queue lag, retries, and dead-letter counts.
  Use a durable outbox if losing an accepted click event is not acceptable.
- Define retention, privacy, and aggregation policies; avoid collecting visitor identifiers
  unless the product requirement and privacy review explicitly justify them.

## API contract

- `POST /shorten` — validate an HTTP(S) URL, persist a mapping, return code and short URL.
- `GET /{code}` — resolve and return a temporary redirect; return 404 for unknown codes.
- `GET /stats/{code}` — return creation time and aggregate clicks; document the consistency
  window for counts.
- `GET /health` — liveness; add a separate readiness check for dependencies in production.

## Reliability and observability

Measure p50/p95/p99 redirect latency, cache hit rate, database connection saturation, code
collision retries, queue lag, event processing failures, and 4xx/5xx rates. Set explicit
timeouts and bounded retries. Define behavior for Redis outages (database fallback), database
outages (fail closed for new mappings), and analytics outages (redirect continues while the
durable queue/outbox reports backlog).

## Validation plan

1. Contract and integration tests for creation, normalization, redirects, stats, expiration,
   collisions, and invalid input.
2. Load tests with representative hot-key and long-tail distributions; verify latency and
   throughput targets chosen by product owners.
3. Failure tests for PostgreSQL failover, Redis eviction/outage, queue backpressure, duplicate
   events, consumer restart, and recovery without double-counting.
4. Security and abuse tests for rate limits, alias validation, redirect destinations, and
   authorization on administrative/statistics endpoints.

No throughput target is claimed without a measured workload and an agreed SLO.

## Migration from this prototype

Keep the API stable and introduce a storage interface. Migrate SQLite rows to PostgreSQL,
verify row counts and sampled lookups, then cut reads over. Add Redis and asynchronous click
events behind feature flags. Preserve a rollback path until mapping and analytics correctness
are confirmed.
