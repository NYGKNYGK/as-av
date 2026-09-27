"""共享线程池通用配置；修改后重新启动 Python 进程。"""
import os


# 全局线程池容量。NumPy 会释放 GIL，过多线程可能争用内存带宽。
MAX_WORKERS = min(8, os.cpu_count() or 1)
THREAD_NAME_PREFIX = "as-nav"
