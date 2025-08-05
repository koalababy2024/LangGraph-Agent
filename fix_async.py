"""
异步兼容性修复脚本
用于修复 eager_start 参数兼容性问题
"""

import asyncio
import sys
import warnings
import logging

def fix_asyncio_compatibility():
    """修复 asyncio 兼容性问题"""
    
    # 禁用相关警告
    warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*coroutine.*never awaited.*")
    warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*Enable tracemalloc.*")
    
    # 修复 eager_start 参数问题
    if hasattr(asyncio, 'create_task'):
        original_create_task = asyncio.create_task
        
        def patched_create_task(coro, *, name=None, context=None):
            """修复后的 create_task，移除 eager_start 参数"""
            try:
                # 尝试使用原始函数，但不传递 eager_start
                return original_create_task(coro, name=name, context=context)
            except TypeError as e:
                if 'eager_start' in str(e):
                    # 如果是 eager_start 错误，使用更基础的方法
                    if sys.version_info >= (3, 7):
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(coro)
                        if name:
                            task.set_name(name)
                        return task
                    else:
                        return asyncio.ensure_future(coro)
                else:
                    raise
        
        # 替换原始函数
        asyncio.create_task = patched_create_task
        logging.info("✅ AsyncIO 兼容性修复已应用")

    # 进一步修补 Task.__del__ 在事件循环已关闭时的异常
    try:
        from asyncio import Task
        _orig_task_del = Task.__del__

        def _safe_task_del(self):
            loop = getattr(self, "_loop", None)
            if loop is not None and not loop.is_closed():
                # 调用原始 __del__
                _orig_task_del(self)
            # 否则静默跳过，避免 AttributeError: 'NoneType' object has no attribute 'call_exception_handler'
        Task.__del__ = _safe_task_del
    except Exception:
        pass
    
    # 设置事件循环策略
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

if __name__ == "__main__":
    fix_asyncio_compatibility()
