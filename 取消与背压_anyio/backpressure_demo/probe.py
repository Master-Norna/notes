"""Real loopback TCP probes; run.py selects the immutable AnyIO source tree."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager, suppress
import hashlib
import json
import platform
import socket

import anyio

PAYLOAD = bytes(range(256)) * (4 * 1024 * 1024 // 256)
WINDOW = 0.3
TIMEOUT = 20


@asynccontextmanager
async def tcp_pair():
    """AnyIO client receives; a real stdlib TCP peer sends (no mock transport)."""
    loop = asyncio.get_running_loop()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.setblocking(False)
        accepting = asyncio.create_task(loop.sock_accept(listener))
        try:
            async with await anyio.connect_tcp(*listener.getsockname()) as stream:
                peer, _ = await accepting
                with peer:
                    peer.setblocking(False)
                    yield stream, peer
        finally:
            accepting.cancel()
            with suppress(asyncio.CancelledError):
                result = await accepting
                result[0].close()


async def already_cancelled():
    """The upstream regression, with cancellation propagation made explicit."""
    async with tcp_pair() as (stream, _):
        assert not stream._transport.is_reading()
        propagated = False
        with anyio.CancelScope() as scope:
            scope.cancel()
            try:
                await stream.receive()
            except anyio.get_cancelled_exc_class():
                propagated = True
                raise
        return {
            "cancel_propagated": propagated,
            "scope_caught": scope.cancelled_caught,
            "is_reading": stream._transport.is_reading(),
        }


async def cancel_blocked(stream):
    """Wait until receive really blocks, then cancel only its own scope."""
    done = anyio.Event()
    state = {"cancel_propagated": False}

    async def receiving(*, task_status=anyio.TASK_STATUS_IGNORED):
        with anyio.CancelScope() as scope:
            task_status.started(scope)
            try:
                await stream.receive()
            except anyio.get_cancelled_exc_class():
                state["cancel_propagated"] = True
                raise
        state["scope_caught"] = scope.cancelled_caught
        done.set()

    async with anyio.create_task_group() as group:
        scope = await group.start(receiving)
        await anyio.wait_all_tasks_blocked()
        # No peer data has been sent: this is the resumed, pending read path.
        assert not done.is_set()
        assert stream._transport.is_reading()
        assert not stream._protocol.read_queue
        state["was_blocked_and_reading"] = True
        scope.cancel()
        await done.wait()
    state["is_reading"] = stream._transport.is_reading()
    return state


async def blocked_receive():
    async with tcp_pair() as (stream, _):
        return await cancel_blocked(stream)


async def receive_exactly(stream, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunks.extend(await stream.receive(min(65536, size - len(chunks))))
    return bytes(chunks)


async def peer_receive_exactly(loop, peer, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = await loop.sock_recv(peer, size - len(chunks))
        if not chunk:
            raise AssertionError("TCP peer reached EOF too early")
        chunks.extend(chunk)
    return bytes(chunks)


async def backpressure():
    async with tcp_pair() as (stream, peer):
        cancellation = await cancel_blocked(stream)
        loop = asyncio.get_running_loop()
        # Do not await send completion before draining: the fixed version may
        # apply backpressure all the way to the sender, depending on OS buffers.
        sender = asyncio.create_task(loop.sock_sendall(peer, PAYLOAD))
        try:
            start = loop.time()
            await anyio.sleep(WINDOW)  # deliberately NO stream.receive() here
            observed_seconds = loop.time() - start
            queued = sum(map(len, stream._protocol.read_queue))
            reading = stream._transport.is_reading()
            sender_done = sender.done()
            received = await receive_exactly(stream, len(PAYLOAD))
            await sender
            assert received == PAYLOAD

            # A fresh receive must still work, not merely drain the old deque.
            marker = b"still connected"
            await loop.sock_sendall(peer, marker)
            assert await receive_exactly(stream, len(marker)) == marker
            await stream.send(b"ack")
            assert await peer_receive_exactly(loop, peer, 3) == b"ack"
            return {
                "cancellation": cancellation,
                "window_seconds": WINDOW,
                "observed_seconds": round(observed_seconds, 6),
                "queue_bytes": queued,
                "is_reading": reading,
                "sender_done_at_snapshot": sender_done,
                "received_bytes": len(received),
                "sha256": hashlib.sha256(received).hexdigest(),
                "content_equal": True,
                "connection_reused_both_directions": True,
                "is_reading_after_recovery": stream._transport.is_reading(),
            }
        finally:
            sender.cancel()
            with suppress(asyncio.CancelledError):
                await sender


def check_cancellation(result, revision):
    assert result["cancel_propagated"] and result["scope_caught"], result
    assert result["is_reading"] is (revision == "before"), result


def check_backpressure(result, revision):
    check_cancellation(result["cancellation"], revision)
    assert result["is_reading"] is (revision == "before"), result
    if revision == "before":
        assert result["queue_bytes"] > 0, "Old source did not accumulate; repeat the probe"
    # No zero-queue assertion after the fix: in-flight callbacks vary by loop/OS.
    assert result["received_bytes"] == len(PAYLOAD) and result["content_equal"], result
    assert result["sha256"] == hashlib.sha256(PAYLOAD).hexdigest(), result
    assert result["connection_reused_both_directions"], result
    assert not result["is_reading_after_recovery"], result


def run_async(function, loop_choice="default"):
    async def bounded():
        with anyio.fail_after(TIMEOUT):
            return await function()

    options = {"loop_factory": asyncio.SelectorEventLoop} if loop_choice == "selector" else {}
    return anyio.run(bounded, backend="asyncio", backend_options=options)


async def suite():
    return {
        "loop": type(asyncio.get_running_loop()).__name__,
        "already_cancelled": await already_cancelled(),
        "blocked_receive": await blocked_receive(),
        "backpressure": await backpressure(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", choices=("before", "after"), required=True)
    parser.add_argument("--loop", choices=("default", "selector"), default="default")
    args = parser.parse_args()
    result = run_async(suite, args.loop)
    check_cancellation(result["already_cancelled"], args.revision)
    check_cancellation(result["blocked_receive"], args.revision)
    check_backpressure(result["backpressure"], args.revision)
    result.update(revision=args.revision, python=platform.python_version(),
                  platform=platform.platform(), anyio_file=anyio.__file__)
    print(json.dumps(result, ensure_ascii=True, indent=2))
