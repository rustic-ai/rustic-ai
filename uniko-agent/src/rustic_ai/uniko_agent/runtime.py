"""Lifecycle ownership for resolver handles without retaining native children."""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import inspect
from pathlib import Path
import threading
from typing import Any
import weakref

from .receipts import ReceiptStore

_accepted_runtime: ContextVar = ContextVar("uniko_accepted_runtime", default=None)


class MemoryRuntime:
    def __init__(
        self, instance: Any, streaming: bool, storage_path: str | None = None, organization_id: str | None = None
    ):
        self.organization_id = organization_id
        self.receipts = ReceiptStore(str(Path(storage_path) / ".rustic-operations.sqlite3") if storage_path else None)
        self.instance = instance
        self.streaming = streaming
        self.closing = False
        self.active = 0
        self.condition = threading.Condition()
        self.handles: weakref.WeakSet = weakref.WeakSet()

    def enter(self):
        with self.condition:
            if self.closing and _accepted_runtime.get() is not self:
                raise RuntimeError("Uniko runtime is shutting down")
            self.active += 1

    @contextmanager
    def operation(self):
        self.enter()
        token = _accepted_runtime.set(self)
        try:
            yield
        finally:
            _accepted_runtime.reset(token)
            self.leave()

    def leave(self):
        with self.condition:
            self.active -= 1
            self.condition.notify_all()

    def wrap(self, value):
        if type(value).__module__.startswith("uniko") and type(value).__name__ in {
            "Agent",
            "Session",
            "Data",
            "Sources",
            "Goals",
            "Goal",
            "Task",
        }:
            return MemoryHandle(value, self)
        return value

    def drop_handles(self):
        for handle in list(self.handles):
            handle._native = None

    def close(self):
        with self.condition:
            self.closing = True
            if self.active:
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    self.condition.wait_for(lambda: self.active == 0)
                else:
                    raise RuntimeError("Use shutdown_async() to drain active work on an event loop")
        self.drop_handles()
        if self.instance is not None:
            self.instance.shutdown_sync()
            self.instance = None
            self.receipts.close()

    async def close_async(self):
        with self.condition:
            self.closing = True
        while self.active:
            await asyncio.sleep(0.005)
        self.drop_handles()
        if self.instance is not None:
            await self.instance.shutdown()
            self.instance = None
            self.receipts.close()


class MemoryHandle:
    """Delegates the native API, tracking accepted work and child-handle ownership."""

    def __init__(self, native: Any, runtime: MemoryRuntime):
        self._native = native
        self._runtime = runtime
        runtime.handles.add(self)

    def __getattr__(self, name):
        if self._native is None:
            raise RuntimeError("Uniko handle has been shut down")
        value = getattr(self._native, name)
        if not callable(value):
            return self._runtime.wrap(value)

        def call(*args, **kwargs):
            self._runtime.enter()
            try:
                if self._native is None:
                    raise RuntimeError("Uniko handle has been shut down")
                result = getattr(self._native, name)(*args, **kwargs)
            except BaseException:
                self._runtime.leave()
                raise
            if inspect.isawaitable(result):
                if hasattr(result, "add_done_callback"):
                    # Native futures may finish even if the caller never awaits
                    # them. Completion, not a retained wrapper, releases work.
                    result.add_done_callback(lambda _: self._runtime.leave())

                    async def wait_future():
                        return self._runtime.wrap(await result)

                    return wait_future()

                async def wait():
                    try:
                        return self._runtime.wrap(await result)
                    finally:
                        self._runtime.leave()

                return wait()
            self._runtime.leave()
            return self._runtime.wrap(result)

        return call
