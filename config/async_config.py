"""
异步配置模块
用于优化AsyncIO任务处理和减少警告
"""

import asyncio
import logging
import warnings
from typing import Any

# 配置日志以减少噪音
def configure_logging():
    """配置日志级别以减少不必要的警告"""
    # 减少HTTP相关日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # 减少AsyncIO相关警告
    warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*coroutine.*never awaited.*")
    warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*Enable tracemalloc.*")

def configure_asyncio():
    """配置AsyncIO以减少任务清理警告"""
    # 设置事件循环策略
    try:
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass
    
    # 设置任务工厂以更好地处理任务清理
    try:
        loop = asyncio.get_event_loop()
        if hasattr(loop, 'set_task_factory'):
            loop.set_task_factory(safe_task_factory)
    except RuntimeError:
        # 没有运行的事件循环
        pass

def safe_task_factory(loop: asyncio.AbstractEventLoop, coro: Any) -> asyncio.Task:
    """安全的任务工厂，用于更好的任务清理"""
    task = asyncio.Task(coro, loop=loop)
    
    # 添加完成回调以确保任务被正确清理
    def task_done_callback(task: asyncio.Task):
        try:
            if task.cancelled():
                return
            exception = task.exception()
            if exception:
                logging.getLogger(__name__).error(f"Task exception: {exception}")
        except Exception:
            # 忽略清理过程中的异常
            pass
    
    task.add_done_callback(task_done_callback)
    return task

def setup_async_environment():
    """设置完整的异步环境"""
    configure_logging()
    configure_asyncio()

# 异步上下文管理器，用于安全的异步操作
class SafeAsyncContext:
    """安全的异步上下文管理器"""
    
    def __init__(self):
        self.tasks = set()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 等待所有任务完成
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
    
    def create_task(self, coro):
        """创建一个被跟踪的任务"""
        try:
            task = asyncio.create_task(coro)
        except TypeError as e:
            if 'eager_start' in str(e):
                # Fallback for eager_start compatibility issues
                loop = asyncio.get_running_loop()
                task = loop.create_task(coro)
            else:
                raise
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

# 安全的睡眠函数
async def safe_sleep(duration: float):
    """安全的异步睡眠，处理取消异常"""
    try:
        await asyncio.sleep(duration)
    except asyncio.CancelledError:
        logging.getLogger(__name__).debug("Sleep cancelled")
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Sleep error: {e}")
        raise
