import asyncio
import pytest
from ai_engine.agents.lock import PipelineLockManager


@pytest.mark.asyncio
async def test_lock_acquires_and_releases():
    mgr = PipelineLockManager()
    async with mgr.acquire("user1", "cv_gen", "pipe1"):
        pass  # should not raise


@pytest.mark.asyncio
async def test_lock_blocks_concurrent_same_user_pipeline():
    mgr = PipelineLockManager()
    order = []

    async def first():
        async with mgr.acquire("user1", "cv_gen", "pipe1"):
            order.append("first_start")
            await asyncio.sleep(0.1)
            order.append("first_end")

    async def second():
        await asyncio.sleep(0.02)  # ensure first starts first
        async with mgr.acquire("user1", "cv_gen", "pipe2"):
            order.append("second_start")

    await asyncio.gather(first(), second())
    assert order == ["first_start", "first_end", "second_start"]


@pytest.mark.asyncio
async def test_lock_allows_different_users_concurrently():
    mgr = PipelineLockManager()
    order = []

    async def user1():
        async with mgr.acquire("user1", "cv_gen", "pipe1"):
            order.append("user1")
            await asyncio.sleep(0.05)

    async def user2():
        async with mgr.acquire("user2", "cv_gen", "pipe2"):
            order.append("user2")
            await asyncio.sleep(0.05)

    await asyncio.gather(user1(), user2())
    assert "user1" in order and "user2" in order


@pytest.mark.asyncio
async def test_lock_timeout():
    mgr = PipelineLockManager(timeout_seconds=0.1)

    async with mgr.acquire("user1", "cv_gen", "pipe1"):
        with pytest.raises(asyncio.TimeoutError):
            async with mgr.acquire("user1", "cv_gen", "pipe2"):
                pass
