# Hebbrix Python SDK

Typed Python client for Hebbrix memory, retrieval, and outcome-learning APIs.

## Install

```bash
pip install hebbrix==2.4.1
```

Python 3.8+ is supported. `MemoryClient` is asynchronous. `SyncMemoryClient`
supports the core collection, memory, search, correction, procedure, and
ProofLoop workflows; advanced temporal, working-memory, consolidation,
memory-tool, and RL resources are currently async-only.

## Quick start

```python
import asyncio
from hebbrix import MemoryClient

async def main():
    async with MemoryClient(api_key="hbx_your_api_key") as client:
        collection = await client.collections.create(name="Support memory")
        memory = await client.memories.create(
            collection_id=collection["id"],
            content="Customer prefers concise replies",
            wait_for_index=True,
            idempotency_key="customer-42-preference-v1",
        )
        results = await client.search(
            "How should replies be formatted?",
            collection_id=collection["id"],
        )
        print(memory, results)

asyncio.run(main())
```

## Durable readiness

Memory writes return either a searchable completion or a durable `202` receipt.
A durable receipt means the database commit succeeded while indexing is still
converging; it is not a failure and does not justify a duplicate write.

When `wait_for_index=True`, the SDK accepts that receipt and polls the documented
status URL. It returns only after `searchable=true`. If the caller's deadline
expires, it raises `IndexingTimeoutError`; the exception retains the original
receipt plus normalized `memory_ids`, `job_id`, `status_url`, `request_id`,
`outbox_event_id`, retry timing, and idempotency replay metadata when available.
The synchronous and asynchronous single, batch, inference-job, and update
readiness paths share this behavior. The SDK never repeats the write while it
polls.

Catch the typed deadline without discarding the durable acceptance:

```python
from hebbrix import IndexingTimeoutError

try:
    created = await client.memories.create(
        content="Customer prefers concise replies",
        wait_for_index=True,
        idempotency_key="customer-42-preference-v1",
        index_timeout=5,
    )
except IndexingTimeoutError as exc:
    # Resume observation; do not submit an unrelated second write.
    if exc.memory_ids:
        created = await client.memories.wait_until_searchable(exc.memory_ids[0])
    elif exc.job_id:
        created = await client.memory_jobs.wait(exc.job_id)
```

For a timed-out batch, pass `exc.receipt` to
`memories.wait_batch_until_searchable(...)`. Alternatively, replay the exact
same body with `exc.idempotency_key`; a changed body with the same key is
rejected by the API rather than creating a second logical write. For an update,
resume polling `exc.memory_ids[0]` because the relational edit already committed.

For an asynchronous batch receipt:

```python
receipt = await client.memories.create_batch(
    [{"content": "First fact"}, {"content": "Second fact"}],
    collection_id="collection-42",
    wait_for_index=False,
    idempotency_key="import-42",
)
completed = await client.memories.wait_batch_until_searchable(receipt)
```

## Pagination

`collections.list()` returns the current page's collection items for backward
compatibility. Use `collections.list_page()` when cursor metadata is required.
Memory resources provide the same `list()`/`list_page()` distinction.

## Advanced capabilities and entitlements

The async client exposes the canonical `/v1` temporal, working-memory,
consolidation, memory-tool, and RL contracts. RL metrics and evaluation require
the Pro plan. Process-wide RL training and checkpoint mutation require an admin
role. Entitlement failures raise `EntitlementError` and preserve the stable
error code, current/required plan, request ID, and support action.

The experimental World Model is intentionally not exported by this public SDK.
It remains withdrawn until a trained, versioned production model artifact and
an end-to-end public serving contract are available.

The authoritative account capability matrix is available from
`GET /v1/users/me/capabilities`.

## Release compatibility

The production API publishes exact build and artifact compatibility at
[`GET /v1/release`](https://api.hebbrix.com/v1/release). The public OpenAPI is
[`/openapi.json`](https://api.hebbrix.com/openapi.json).

- [Documentation](https://docs.hebbrix.com)
- [API reference](https://api.hebbrix.com/docs)
- [PyPI files](https://pypi.org/project/hebbrix/#files)
- [Support](https://www.hebbrix.com/contact)

## License

MIT. See `LICENSE` in the distribution.
