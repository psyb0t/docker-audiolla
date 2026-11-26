from __future__ import annotations

import asyncio
import logging
import multiprocessing
import pickle
import socket
import struct
from collections.abc import Callable
from contextlib import suppress
from multiprocessing.process import BaseProcess
from typing import Any

from anyio import CancelScope
from fastapi import HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException


class ModelProcessError(RuntimeError):
    pass


_log = logging.getLogger(__name__)
_FRAME = struct.Struct("!I")
_STOP_TIMEOUT = 5.0
_HTTP_ERROR = "http"


async def _receive(reader: asyncio.StreamReader) -> Any:
    (size,) = _FRAME.unpack(await reader.readexactly(_FRAME.size))
    # Only the spawned child and its parent have this private socket.
    return pickle.loads(await reader.readexactly(size))  # noqa: S301


async def _send(writer: asyncio.StreamWriter, message: Any) -> None:
    payload = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    writer.write(_FRAME.pack(len(payload)))
    writer.write(payload)
    await writer.drain()


async def _serve(
    sock: socket.socket, factory: Callable[..., Any], args: tuple[Any, ...]
) -> None:
    worker = factory(*args)
    reader, writer = await asyncio.open_connection(sock=sock)

    async def run(request: tuple[int, str, tuple[Any, ...], dict[str, Any]]) -> None:
        request_id, operation, args, kwargs = request
        failed: bool | str
        try:
            result = await worker.execute(operation, *args, **kwargs)
        except StarletteHTTPException as exc:
            result = (exc.status_code, exc.detail, exc.headers)
            failed = _HTTP_ERROR
        except Exception as exc:  # noqa: BLE001
            # Relay backend errors so HTTP and MCP keep their existing error handling.
            try:
                pickle.loads(pickle.dumps(exc))  # noqa: S301
            except (pickle.PickleError, AttributeError, TypeError):
                _log.exception("could not serialize model worker error")
                exc = ModelProcessError("model worker operation failed")
            result = exc
            failed = True
        else:
            failed = False
        try:
            await _send(writer, (request_id, failed, result, worker.resident()))
        except (pickle.PickleError, TypeError, AttributeError):
            _log.exception("could not serialize model worker response")
            await _send(
                writer,
                (
                    request_id,
                    True,
                    ModelProcessError("invalid model worker response"),
                    None,
                ),
            )
        except ConnectionError:
            _log.debug("model worker client disconnected")

    tasks: set[asyncio.Task[None]] = set()
    try:
        while True:
            request = await _receive(reader)
            task = asyncio.create_task(run(request))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
    except asyncio.IncompleteReadError:
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        writer.close()
        with suppress(ConnectionError):
            await writer.wait_closed()
        await worker.close()


def _start(
    sock: socket.socket, factory: Callable[..., Any], args: tuple[Any, ...]
) -> None:
    with sock:
        asyncio.run(_serve(sock, factory, args))


class ModelProcess:
    """Own a lazy worker and reap it before reporting successful eviction."""

    def __init__(self, factory: Callable[..., Any], *args: Any) -> None:
        self._factory = factory
        self._args = args
        self._process: BaseProcess | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._lifecycle = asyncio.Lock()
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._resident: Any = None

    @property
    def busy(self) -> bool:
        return bool(self._pending) or self._lifecycle.locked()

    @property
    def resident(self) -> Any:
        return self._resident if self._writer is not None else None

    async def _read(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                request_id, failed, result, self._resident = await _receive(reader)
                future = self._pending.get(request_id)
                if future is None or future.done():
                    continue
                if failed == _HTTP_ERROR:
                    future.set_exception(HTTPException(*result))
                elif failed:
                    future.set_exception(result)
                else:
                    future.set_result(result)
        except (
            asyncio.IncompleteReadError,
            ConnectionError,
            pickle.PickleError,
            TypeError,
        ):
            if self._pending:
                _log.exception("model worker connection lost")
        finally:
            self._writer = None
            writer.close()
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ModelProcessError("model worker disconnected"))

    async def _connect(self) -> asyncio.StreamWriter:
        async with self._lifecycle:
            if self._writer is not None:
                return self._writer
            await self._stop()
            parent, child = socket.socketpair()
            try:
                with child:
                    process = multiprocessing.get_context("spawn").Process(
                        target=_start, args=(child, self._factory, self._args)
                    )
                    process.start()
                    self._process = process
                reader, writer = await asyncio.open_connection(sock=parent)
            except BaseException:
                parent.close()
                await self._stop()
                raise
            self._writer = writer
            self._reader_task = asyncio.create_task(self._read(reader, writer))
            return writer

    async def call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        writer = await self._connect()
        self._next_id += 1
        request_id = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await _send(writer, (request_id, operation, args, kwargs))
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # The caller may still own paths or buffers that the child is using.
            with CancelScope(shield=True):
                await asyncio.gather(future, return_exceptions=True)
            raise
        except ConnectionError as exc:
            raise ModelProcessError("model worker disconnected") from exc
        finally:
            self._pending.pop(request_id, None)
            if future.done() and not future.cancelled():
                future.exception()

    async def stop(self) -> None:
        async with self._lifecycle:
            with CancelScope(shield=True):
                await self._stop()

    async def _stop(self) -> None:
        process = self._process
        if process is None:
            return
        if self._writer is not None:
            self._writer.close()
        if self._reader_task is not None:
            await self._reader_task
            self._reader_task = None
        await asyncio.to_thread(process.join, _STOP_TIMEOUT)
        if process.is_alive():
            _log.warning(
                "model worker did not shut down, killing it", extra={"pid": process.pid}
            )
            process.kill()
            await asyncio.to_thread(process.join)
        process.close()
        self._process = None
        self._resident = None
