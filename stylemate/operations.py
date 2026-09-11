"""Bounded, process-local admission control; no credentials stored in counters."""

import hashlib
import threading
import time
from contextlib import contextmanager


class BusyError(RuntimeError):
    pass


class OperationGate:
    def __init__(self, limit=8, window=600, cooldown=10, concurrency=3, clock=time.monotonic):
        self.limit, self.window, self.cooldown = limit, window, cooldown
        self.concurrency, self.clock = concurrency, clock
        self.lock = threading.Lock()
        self.history = {}
        self.active = set()
        self.active_count = 0

    @contextmanager
    def claim(self, session_id, *api_keys):
        identities = {"session:" + session_id}
        identities.update("key:" + hashlib.sha256(key.encode()).hexdigest() for key in api_keys)
        with self.lock:
            now = self.clock()
            self.history = {k: [t for t in v if now - t < self.window]
                            for k, v in self.history.items() if v and now - v[-1] < self.window}
            if (self.active_count >= self.concurrency or any(k in self.active for k in identities)):
                raise BusyError("已有任务运行或服务繁忙，请等待任务完成。")
            for identity in identities:
                recent = self.history.get(identity, [])
                if len(recent) >= self.limit or (recent and now - recent[-1] < self.cooldown):
                    raise BusyError("操作过于频繁：至少间隔 10 秒，每 10 分钟最多 8 次。")
            for identity in identities:
                self.history.setdefault(identity, []).append(now)
                self.active.add(identity)
            self.active_count += 1
        try:
            yield
        finally:
            with self.lock:
                self.active.difference_update(identities)
                self.active_count -= 1


GATE = OperationGate(concurrency=3)
