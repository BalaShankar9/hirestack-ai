"""Standalone L2 sandbox sidecar entrypoint (m11-pr44).

Runs the gRPC sandbox server as a long-lived process. Used by the
``tool-runner`` service in ``infra/docker-compose.yml`` (profile
``l2-sandbox``).

Configuration via env:
* ``L2_SANDBOX_HOST`` (default ``0.0.0.0``)
* ``L2_SANDBOX_PORT`` (default ``50051``)

The server uses the canonical ``RESOLVERS`` map from
``ai_engine.registry.resolvers``. As long as that map is empty
(default until m7-pr29b lands more resolvers), every Invoke RPC
returns ``UnknownCodeRef`` — same shadow-mode contract as L1.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from ai_engine.registry.grpc_sandbox import start_inproc_server

logger = logging.getLogger(__name__)


async def _run() -> None:
    host = os.getenv("L2_SANDBOX_HOST", "0.0.0.0")
    port = int(os.getenv("L2_SANDBOX_PORT", "50051"))
    handle = await start_inproc_server(host=host, port=port)
    logger.info("l2_sandbox_listening", extra={"target": handle.target})

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler; fall back
            # to sync signal.signal which sets the flag.
            signal.signal(sig, lambda *_: stop_event.set())

    await stop_event.wait()
    logger.info("l2_sandbox_stopping")
    await handle.server.stop(grace=5.0)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
