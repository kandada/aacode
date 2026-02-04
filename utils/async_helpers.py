# 异步助手
# utils/async_helpers.py
"""
异步辅助工具集
"""
import asyncio
import functools
from typing import Any, Callable, TypeVar, Coroutine
from concurrent.futures import ThreadPoolExecutor
import inspect

T = TypeVar('T')


class AsyncHelpers:
    """异步辅助工具类"""

    @staticmethod
    def run_sync(func: Callable[..., T], *args, **kwargs) -> T:
        """
        同步运行函数（在异步环境中调用同步函数）

        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数结果
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            raise e

    @staticmethod
    async def run_sync_in_executor(func: Callable[..., T], *args, **kwargs) -> T:
        """
        在线程池中运行同步函数

        Args:
            func: 同步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数结果
        """
        loop = asyncio.get_event_loop()

        # 使用functools.partial包装函数和参数
        partial_func = functools.partial(func, *args, **kwargs)

        # 在线程池中执行
        return await loop.run_in_executor(None, partial_func)

    @staticmethod
    def to_async(func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
        """
        将同步函数转换为异步函数

        Args:
            func: 同步函数

        Returns:
            异步函数
        """
        if inspect.iscoroutinefunction(func):
            return func

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await AsyncHelpers.run_sync_in_executor(func, *args, **kwargs)

        return async_wrapper

    @staticmethod
    async def with_timeout(coro: Coroutine, timeout: float, default: Any = None) -> Any:
        """
        带超时的协程执行

        Args:
            coro: 协程
            timeout: 超时时间（秒）
            default: 超时时的默认返回值

        Returns:
            协程结果或默认值
        """
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            return default
        except Exception:
            raise

    @staticmethod
    async def parallel_execute(tasks: list, max_concurrent: int = 5) -> list:
        """
        并行执行多个异步任务

        Args:
            tasks: 异步任务列表
            max_concurrent: 最大并发数

        Returns:
            结果列表
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(task):
            async with semaphore:
                return await task

        # 创建任务
        wrapped_tasks = [run_with_semaphore(task) for task in tasks]

        # 并行执行
        return await asyncio.gather(*wrapped_tasks, return_exceptions=True)

    @staticmethod
    async def retry_async(
            func: Callable[..., Coroutine],
            max_retries: int = 3,
            delay: float = 1.0,
            backoff: float = 2.0,
            exceptions: tuple = (Exception,)
    ) -> Any:
        """
        带重试的异步函数执行

        Args:
            func: 异步函数
            max_retries: 最大重试次数
            delay: 初始延迟（秒）
            backoff: 退避因子
            exceptions: 需要重试的异常类型

        Returns:
            函数结果
        """
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return await func()
            except exceptions as e:
                last_exception = e

                if attempt == max_retries:
                    break

                # 计算等待时间
                wait_time = delay * (backoff ** attempt)
                print(f"🔄 重试 {attempt + 1}/{max_retries}, 等待 {wait_time:.1f}秒: {str(e)[:100]}")

                await asyncio.sleep(wait_time)

        raise last_exception or Exception("重试失败")

    @staticmethod
    def create_async_queue(maxsize: int = 100):
        """
        创建异步队列

        Args:
            maxsize: 队列最大大小

        Returns:
            异步队列
        """
        return asyncio.Queue(maxsize=maxsize)

    @staticmethod
    async def process_queue(
            queue: asyncio.Queue,
            processor: Callable[[Any], Coroutine],
            worker_count: int = 3
    ):
        """
        处理队列中的项目

        Args:
            queue: 异步队列
            processor: 项目处理函数
            worker_count: 工作协程数量
        """

        async def worker():
            while True:
                try:
                    item = await queue.get()

                    if item is None:  # 停止信号
                        queue.task_done()
                        break

                    try:
                        await processor(item)
                    except Exception as e:
                        print(f"❌ 处理项目失败: {e}")

                    queue.task_done()

                except asyncio.CancelledError:
                    break

        # 创建工作协程
        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]

        try:
            # 等待队列处理完成
            await queue.join()
        finally:
            # 发送停止信号
            for _ in range(worker_count):
                await queue.put(None)

            # 等待工作协程完成
            await asyncio.gather(*workers, return_exceptions=True)

    @staticmethod
    async def run_periodic(
            func: Callable[[], Coroutine],
            interval: float,
            stop_event: asyncio.Event = None
    ):
        """
        定期运行函数

        Args:
            func: 异步函数
            interval: 运行间隔（秒）
            stop_event: 停止事件
        """
        stop_event = stop_event or asyncio.Event()

        while not stop_event.is_set():
            try:
                await func()
            except Exception as e:
                print(f"❌ 定期任务失败: {e}")

            # 等待间隔时间或停止事件
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue  # 继续下一次执行


# 方便的函数别名
run_sync = AsyncHelpers.run_sync
run_sync_in_executor = AsyncHelpers.run_sync_in_executor
to_async = AsyncHelpers.to_async
with_timeout = AsyncHelpers.with_timeout
parallel_execute = AsyncHelpers.parallel_execute
retry_async = AsyncHelpers.retry_async
create_async_queue = AsyncHelpers.create_async_queue
process_queue = AsyncHelpers.process_queue
run_periodic = AsyncHelpers.run_periodic



