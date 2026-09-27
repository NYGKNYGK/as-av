"""进程内共享线程池；导入模块时创建执行器，工作线程按任务需求启动。

所有模块统一使用 ``from src import thread_pool``：
    values = thread_pool.run_tasks(function, items)
    future = thread_pool.POOL.submit(function, argument)

run_tasks 保持输入顺序，并在共享池的工作线程内自动串行执行嵌套批次，
避免工作线程占满后相互等待。直接 submit 的任务不要阻塞等待同一池的新任务。
业务模块不要对 POOL 使用 with 或 shutdown；解释器退出时由标准库等待任务并
回收线程。配置在导入时生效，不通过反复 reload 或创建线程池调整容量。
"""
from concurrent.futures import ThreadPoolExecutor, wait
from numbers import Integral
from threading import local

from .config import thread_pool_config as config


if isinstance(config.MAX_WORKERS, bool) or not isinstance(config.MAX_WORKERS, Integral) or config.MAX_WORKERS < 1:
    raise ValueError("MAX_WORKERS 必须是正整数")

MAX_WORKERS = int(config.MAX_WORKERS)
_worker_state = local()


def _initialize_worker():
    _worker_state.active = True


def in_worker_thread() -> bool:
    """当前线程是否属于本模块的共享线程池。"""
    return getattr(_worker_state, "active", False)


POOL = ThreadPoolExecutor(max_workers=MAX_WORKERS,
                          thread_name_prefix=config.THREAD_NAME_PREFIX,
                          initializer=_initialize_worker)


def run_tasks(function, tasks, *, parallel: bool = True) -> list:
    """同步执行一批单参数任务，按输入顺序返回结果，异常时先收拢已提交任务。"""
    if not parallel or MAX_WORKERS == 1 or in_worker_thread():
        return list(map(function, tasks))
    futures = []
    try:
        for task in tasks:
            futures.append(POOL.submit(function, task))
        return [future.result() for future in futures]
    finally:
        # 成功时均已结束；失败时取消未启动任务、等待正在运行的任务结束。
        # 这只处理本次调用的任务，不影响其他模块，也不会关闭共享池。
        for future in futures:
            future.cancel()
        wait(futures)
