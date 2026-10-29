# receive() Was Cancelled. Why Is TCP Still Reading? A Backpressure Fix in AnyIO

Put a timeout around a network receive, move on to other work when it expires, and keep the connection for later. It is an ordinary pattern:

```python
with anyio.move_on_after(0.1):
    data = await stream.receive()

# Stop receiving for now, but keep the connection open
```

Before this fix, AnyIO's asyncio backend could leave behind a less obvious state: `receive()` had exited because of the timeout, but the underlying TCP transport was still reading. Data sent by the peer would keep entering a receive queue in Python, even though the application was no longer consuming it.

**Cancelling the wait does not undo the reading that was enabled before it.**

This was fixed in [AnyIO #1424](https://github.com/agronholm/anyio/pull/1424), merged on October 18, 2026. The production change simply wrapped one `await` in `try/finally`. To see why those two lines matter, we first need to separate “the application is receiving” from “the transport is reading.”

## 1. Data Can Enter Python Without an Application Calling receive()

Data on a TCP connection does not jump straight from the network into the return value of `await stream.receive()`. This asyncio path in AnyIO has several layers:

- The operating system receives TCP data into a kernel buffer.
- The asyncio transport passes the data it reads to the protocol's `data_received()` callback.
- AnyIO's protocol puts the data in `read_queue`, and the application's `receive()` takes it out.

Here, *protocol* means asyncio's callback interface, not another network protocol layered on top. It accepts bytes from the transport, and the relevant code is short ([StreamProtocol](https://github.com/agronholm/anyio/blob/6219807568bd7c32f2c08f923c7d93f95c836127/src/anyio/_backends/_asyncio.py#L1335-L1362), excerpt):

```python
# When the connection is established
self.read_queue = deque()

# When the transport delivers data
def data_received(self, data: bytes) -> None:
    self.read_queue.append(bytes(data))
    self.read_event.set()
```

`read_event` wakes a waiting receiver; `read_queue` stores the data. This `deque()` has no capacity limit, and `data_received()` has no check to pause reading once the queue reaches a certain size.

So what normally keeps it from growing indefinitely? The answer is `receive()`. AnyIO does not leave reading enabled and wait for the queue to fill up. Instead, it resumes reading when it needs to wait for new data, then pauses reading once data arrives. A newly established client connection also starts with a call to `pause_reading()` ([connect_tcp](https://github.com/agronholm/anyio/blob/6219807568bd7c32f2c08f923c7d93f95c836127/src/anyio/_backends/_asyncio.py#L2915-L2926)).

`pause_reading()` pauses the transport's delivery of data to the protocol. When the application stops consuming for a while, this keeps data from being continually moved into the Python queue. As the kernel receive buffer fills, TCP flow control gradually pushes the pressure back to the sender. That is backpressure here: if the receiver cannot keep up, the process should not hide that fact by storing data without limit.

Pausing reading does not close the connection, nor does it guarantee that the peer's next `send()` will block immediately. Kernel buffers, the peer's send buffer, and data in flight still exist. The first thing it shuts off is the path that keeps delivering data to this protocol ([asyncio ReadTransport documentation](https://docs.python.org/3.12/library/asyncio-protocol.html#asyncio.ReadTransport.pause_reading)).

## 2. Cancellation Worked; the Pause After It Was Missing

Before the fix, the branch of `receive()` that waits for new data did these three things ([pre-fix source](https://github.com/agronholm/anyio/blob/633965bad02a857574b3dbad03d1ef9f35e9caa4/src/anyio/_backends/_asyncio.py#L1417-L1457)):

```python
self._transport.resume_reading()
await self._protocol.read_event.wait()
self._transport.pause_reading()
```

Without cancellation, the logic is straightforward: enable reading, wait for data, pause reading, then take a chunk from the queue and return it. If the chunk is too large, return only `max_bytes` and put the remainder back at the front of the queue.

The problem is that the `await` in the middle is not guaranteed to return normally.

When `move_on_after()` expires, it cancels the operation inside its scope. If the receiving task is blocked in `read_event.wait()`, a cancellation exception is raised at that wait point. Control leaves the branch without ever executing the next line, `pause_reading()`. `receive()` has exited, but the state change it made to the transport is still in effect.

If the peer now sends data, two things happen that no longer work together:

1. The transport is still reading, so `data_received()` keeps appending bytes to the queue.
2. The original receiving task has exited, so nobody is taking data out.

`read_event.set()` can signal that data is available. It cannot bring back a cancelled consumer, and it does not pause the transport either. If the application does not call `receive()` again for some time, the queue can keep growing.

| State after the same receive is cancelled | Before the fix | After the fix |
|---|---|---|
| Cleanup when leaving the wait | `pause_reading()` is skipped | `finally` calls `pause_reading()` |
| Transport reading | Still enabled | Paused |
| Subsequent delivery to the protocol's queue | Continues without a consumer | Paused |

This is why “cancellation succeeded” and “state was restored correctly” are separate questions. The cancellation exception could already end the wait as intended. What was missing was the cleanup when the wait ended.

## 3. finally Revokes Permission to Read, Not the Connection

[The final change in #1424](https://github.com/agronholm/anyio/commit/6219807568bd7c32f2c08f923c7d93f95c836127) moved the pause into `finally`:

```python
self._transport.resume_reading()
try:
    await self._protocol.read_event.wait()
finally:
    self._transport.pause_reading()
```

This pairs “enable reading when starting to wait” with “pause reading when leaving the wait.” Reading must pause after data arrives normally, and it must also pause if the wait is cancelled.

The code does not catch the cancellation exception or return a fake empty byte string. After `finally` runs, cancellation still propagates outward to be handled by its cancellation scope. Pausing is a synchronous call, so cleanup does not require another `await`.

Nor does the fix call `close()` or clear the queue. Cancelling one receive does not mean the application is abandoning the entire connection. On the next receive, data already in the queue can still be taken out, and reading can be resumed with `resume_reading()` when more data is needed. If data arrives around the time of cancellation, bytes already queued should not be discarded as a side effect of that cancellation.

**The fix preserves cancellation, the connection, and data already received; it simply stops an exited receive call from leaving reading enabled.**

## 4. Seeing the Difference over a Real TCP Connection

The accompanying [backpressure_demo](backpressure_demo/README.md) loads AnyIO source from two pinned commits and runs the same experiment in separate processes:

- Before the fix: [`633965b`](https://github.com/agronholm/anyio/tree/633965bad02a857574b3dbad03d1ef9f35e9caa4), the parent of the merge commit.
- After the fix: [`6219807`](https://github.com/agronholm/anyio/tree/6219807568bd7c32f2c08f923c7d93f95c836127), the final merge commit.

The experiment uses a local IPv4 loopback TCP connection. First, it lets the receiving task actually enter the wait, confirms that transport reading is enabled, and then cancels the task. Once the receiving task has exited, the peer starts sending 4 MiB. The receiver makes no further `receive()` calls during a 0.3-second observation window. It then resumes receiving, checks the contents byte for byte, and transfers a new message over the same connection.

On Windows 11 with CPython 3.12.14 and the default `ProactorEventLoop`, the results were:

| Observation | Before the fix | After the fix |
|---|---:|---:|
| `transport.is_reading()` after cancellation completes | `True` | `False` |
| Bytes in `read_queue` after 0.3 seconds | 4,194,304 (4 MiB) | 0 |
| Data obtained after receiving resumes | 4 MiB, contents match | 4 MiB, contents match |
| Continued bidirectional use of the same connection | Works | Works |

The old code moved all 4 MiB into the Python queue. The fixed code stopped delivering data to that queue, but did not lose the data: once receiving resumed, all 4 MiB arrived intact, and the connection remained usable.

At this observation point, the sending task had already finished in both cases. That usefully separates two ideas: data can be accepted into system buffers without having entered AnyIO's Python queue. The fix restores backpressure on the reading side; it does not force every send by the peer to wait immediately.

The accompanying project repeated the experiment 10 times per source snapshot on each of the default loop and the Windows Selector loop. Every queue snapshot matched the 4 MiB / 0 result above, and all checks for cancellation propagation, data integrity, and connection reuse passed. From the `backpressure_demo` directory, run:

```powershell
python -m pip install -r requirements.txt
python run.py --test
```

The first run downloads both pinned source snapshots; subsequent runs can use the cache with `--offline`. `--test` runs three integration tests against each snapshot. Passing against the old code means the faulty state was successfully reproduced. Only passing against the fixed code means reading returned to the paused state.

The buffered byte count here is `sum(len(chunk) for chunk in stream._protocol.read_queue)`, not process RSS. It does not include kernel buffers or data that may be held inside the transport. Private attributes are used only to observe the implementation at these pinned commits.

4 MiB is the payload chosen for the experiment, not an upper bound on the bug. Likewise, 0.3 seconds is an observation window, not a throughput benchmark. A different event loop, operating system, or load can change how many bytes arrive within that window. The key comparison is whether the transport is still reading after cancellation completes, and whether the full data can be delivered when receiving resumes.

## 5. Why TLS Can Take the Same Path

Adding TLS to a connection does not automatically restore the underlying TCP reading state.

AnyIO's [TLSStream.receive()](https://github.com/agronholm/anyio/blob/6219807568bd7c32f2c08f923c7d93f95c836127/src/anyio/streams/tls.py#L264-L272) tries to obtain plaintext from the SSL object. When that object needs more network data, `_call_sslobject_method()` reaches this line ([source](https://github.com/agronholm/anyio/blob/6219807568bd7c32f2c08f923c7d93f95c836127/src/anyio/streams/tls.py#L201-L217)):

```python
data = await self.transport_stream.receive()
```

When `transport_stream` is a TCP `SocketStream` from the asyncio backend, the wait comes back to the same `receive()` discussed above. Cancellation here can likewise skip the pause in the old code. The bytes that subsequently enter the underlying queue are TLS ciphertext; the upper layer does not have to be actively decrypting or consuming plaintext for this to happen.

TLS handles encryption and decryption. It does not supply the backpressure missing from the underlying receive queue. This section explains the shared call path; the 4 MiB experiment above used plain TCP.

## 6. Why the Regression Test Does Not Need to Send 4 MiB

Queue growth over a real connection shows the consequence, but a test that prevents this particular bug from returning can be more direct.

The regression test merged with the PR does not keep feeding data and watch memory grow. It establishes a TCP connection, calls `receive()` inside an already-cancelled scope, and checks the transport state after leaving that scope ([upstream test](https://github.com/agronholm/anyio/blob/6219807568bd7c32f2c08f923c7d93f95c836127/tests/test_sockets.py#L266-L276), excerpt):

```python
async with await connect_tcp(*server_addr) as stream:
    with CancelScope() as scope:
        scope.cancel()
        await stream.receive()

    assert not stream._transport.is_reading()
```

Calling `scope.cancel()` first does not mean that the Python statements after it stop executing. For this connection, which has no data yet, `receive()` still reaches `resume_reading()` and then encounters cancellation at the wait point. The old code skips the pause; the new code enters `finally`. This short test targets exactly where the two paths diverge.

The approach came from the maintainer's [review suggestion](https://github.com/agronholm/anyio/pull/1424#discussion_r4306515133). It does not need to demonstrate the entire TCP flow-control process. It only needs to pin down the immediate cause of this bug: reading should not remain enabled after a receive is cancelled. Cancelling a receive that has actually blocked, observing queue growth, and checking that the connection remains usable are explored by the accompanying reproduction.

## Closing Thoughts

The failure was not about whether cancellation arrived, but about who restored the state changed before the wait once cancellation did arrive.

`resume_reading()` does not automatically stop taking effect when the receiving task ends. It changes persistent state on another object: the transport. Putting `pause_reading()` on the line after `await` handles only a normal return. Putting it in `finally` makes the reading temporarily enabled for this receive end along with the wait.

For the original report and reproduction, see [#1423](https://github.com/agronholm/anyio/issues/1423); for the fix and discussion, see [#1424](https://github.com/agronholm/anyio/pull/1424).
