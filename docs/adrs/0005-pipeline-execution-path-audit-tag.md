# ADR-0005: Pipeline events MUST carry an `execution_path` audit tag

Date: 2026-04-28
Status: Accepted

## Context

The pipeline runtime supports two execution paths:

- **Agent path** — the orchestrator-driven multi-agent flow (recon → atlas → cipher → quill → forge → sentinel → nova).
- **Legacy path** — the pre-orchestrator monolithic generator, kept behind the `LEGACY_PIPELINE_ALLOWED` feature gate as a recovery hatch.

Production-readiness requires being able to answer one question for every emitted event row in `generation_job_events`:

> Which code path produced this event?

Without that tag, observability of which path is actually serving traffic devolves to log spelunking, and a regression that silently routes everything to legacy is invisible until customers complain.

The original `PipelineRuntime` set `_execution_path` on itself but did not stamp the value onto outgoing events. Some sinks (DatabaseSink) read it via private attribute access; most callers had no observable signal at all.

## Decision

Every `PipelineEvent` emitted by `PipelineRuntime` carries an `execution_path` key inside `event.data`. The runtime guarantees this by wrapping the caller-supplied sink in a small adapter:

```python
self.sink = _ExecutionPathTaggingSink(
    inner=event_sink or NullSink(),
    runtime=self,
)
```

`_ExecutionPathTaggingSink.emit` does:

```python
event.data.setdefault("execution_path", self._runtime._execution_path)
return await self._inner.emit(event)
```

Three invariants hold:

1. **Always wrap.** The wrap happens unconditionally in `__init__`; even a `None` sink becomes `_ExecutionPathTaggingSink(NullSink(), runtime=self)`. There is no path that bypasses the tagging adapter.
2. **`setdefault` semantics.** Explicit overrides from upstream (e.g., a parent runtime that has already tagged the event) win — the wrapper only fills in the tag if absent.
3. **Transparent forwarding.** `__getattr__` proxies arbitrary attribute access to the inner sink, and `close()` propagates. The adapter is invisible to anything that holds a `runtime.sink` reference and treats it like the raw sink.

## Enforcement

`backend/tests/unit/test_execution_path_tagging_sink.py` pins all three invariants: that the wrap always happens, that the tag is stamped on emit, that explicit overrides survive, that `event.data is None` is defended against, that attribute access is transparent, and that close() propagates.

The `EXECUTION_PATH_AGENT` / `EXECUTION_PATH_LEGACY` / `EXECUTION_PATH_UNKNOWN` constants live in `ai_engine.agents.event_taxonomy` so both runtime and consumers (DatabaseSink, observability dashboards) read from one place.

## Consequences

- A single grep on `execution_path` in `generation_job_events.payload` cleanly partitions traffic between agent and legacy paths.
- Future sinks (telemetry, audit log shipper, replay debugger) get the tag for free.
- Any future refactor of `PipelineRuntime.__init__` that drops the wrap is caught at CI by the "always wrap" invariant test.
- Removing the legacy path (post P4-S10 in production) becomes auditable: when the agent-path event count is 100% of total for a sustained window, the gate can be pulled with confidence.
