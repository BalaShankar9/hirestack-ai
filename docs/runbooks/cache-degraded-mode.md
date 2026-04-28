# Runbook: Cache degraded mode (Redis unreachable)

Applies to `app.core.cache`. The cache layer is best-effort — when
Redis is unreachable, the module falls back to a 512-entry
in-memory `OrderedDict` LRU per process.

## Symptom

- `/health` shows `redis.connected: false`.
- `/healthz/ready` continues to return 200 (Redis is optional —
  see ADR-0003).
- Latency may rise modestly on cache-hit-heavy endpoints because
  per-process caches don't share state across replicas.

## Why this is OK (most of the time)

- All `cache_get` / `cache_set` failures are swallowed and logged at
  WARN. Application logic never breaks because the cache went away.
- The in-memory LRU holds the most-recent 512 entries per pod.
  Hot keys still hit; cold-start traffic falls through to the
  upstream (Supabase / AI providers — both protected by their own
  breakers, see ADR-0001).

## Investigate

```bash
curl -s "$BACKEND_URL/health" | jq '.redis'
```

If the error is timeout-y or DNS-y:

1. Confirm `REDIS_URL` env var is set and unchanged on the deploy.
2. From a pod, `redis-cli -u "$REDIS_URL" ping`. Expected: `PONG`.
3. Check the Redis provider dashboard (Upstash / Railway addon /
   etc.) for incidents.

## Decide

| Situation                          | Action                                          |
|------------------------------------|-------------------------------------------------|
| Redis provider reports an outage   | Wait. App is degraded but functional.           |
| `REDIS_URL` rotated and stale      | Redeploy with the new value.                    |
| Pod cannot reach Redis (egress)    | Check VPC / peering / IP allowlist on Redis.    |
| Redis is up but slow (>1 s ping)   | Scale Redis tier; consider connection pool size. |

## Capacity warning

The in-memory LRU cap is 512 entries **per process**. Sustained
traffic to a high-cardinality keyspace (e.g. per-user feature
flags) during a Redis outage will see degraded hit rates. Treat
extended Redis outages (>30 min) as a P2 incident — file a
follow-up to surface a `cache_hit_rate` metric if not already
emitted.

## Recovery

When Redis returns, no action is required. The next `cache_set` or
`cache_get` call lazily re-establishes the connection via
`get_redis()`. The in-memory cache continues to coexist; entries
written during the outage are not migrated to Redis.
