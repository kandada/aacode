"""异步助手测试"""

import asyncio
import pytest
from utils.async_helpers import AsyncHelpers


class TestAsyncHelpers:
    """异步助手测试类"""

    def test_run_sync(self):
        """测试run_sync方法"""
        helpers = AsyncHelpers()

        def sync_function(x, y):
            return x + y

        result = helpers.run_sync(sync_function, 3, 4)
        assert result == 7

    def test_run_sync_in_executor(self):
        """测试在线程池中运行同步函数"""

        async def test():
            helpers = AsyncHelpers()

            def cpu_intensive_function(x, y):
                # 模拟CPU密集型操作
                return x * y

            result = await helpers.run_sync_in_executor(cpu_intensive_function, 5, 6)
            assert result == 30

        asyncio.run(test())

    def test_to_async(self):
        """测试将同步函数转换为异步函数"""
        helpers = AsyncHelpers()

        def sync_function(x, y):
            return x + y

        async_function = helpers.to_async(sync_function)

        async def test():
            result = await async_function(3, 4)
            assert result == 7

        asyncio.run(test())

    def test_with_timeout(self):
        """测试带超时的异步函数"""

        async def test():
            helpers = AsyncHelpers()

            async def fast_function():
                await asyncio.sleep(0.1)
                return "success"

            # 成功情况
            result = await helpers.with_timeout(fast_function(), timeout=1.0)
            assert result == "success"

            # 超时情况
            async def slow_function():
                await asyncio.sleep(1.0)
                return "should timeout"

            result = await helpers.with_timeout(
                slow_function(), timeout=0.1, default="timeout"
            )
            assert result == "timeout"

        asyncio.run(test())

    def test_parallel_execute(self):
        """测试并行执行任务"""

        async def test():
            helpers = AsyncHelpers()

            async def task1():
                await asyncio.sleep(0.1)
                return "task1"

            async def task2():
                await asyncio.sleep(0.05)
                return "task2"

            async def task3():
                await asyncio.sleep(0.2)
                return "task3"

            tasks = [task1(), task2(), task3()]
            results = await helpers.parallel_execute(tasks, max_concurrent=2)
            assert set(results) == {"task1", "task2", "task3"}

        asyncio.run(test())

    def test_retry_async(self):
        """测试异步重试"""

        async def test():
            helpers = AsyncHelpers()

            call_count = 0

            async def flaky_function():
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ValueError(f"Attempt {call_count} failed")
                return "success"

            result = await helpers.retry_async(
                flaky_function, max_retries=3, delay=0.01, backoff=1.0
            )

            assert result == "success"
            assert call_count == 3

        asyncio.run(test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
