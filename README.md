# Hebbrix Python SDK

Typed Python client for Hebbrix memory, retrieval, and outcome-learning APIs.

This branch is the **2.6.0rc2 prerelease**. The new policy configuration and
advice helpers require backend schema `e5f6g7h8i868` or a compatible successor.
A prerelease SDK does not enable autonomous execution. ASK/REVIEW/ACT is advice;
an action still requires independent permission.

## Install

```bash
pip install hebbrix==2.6.0rc2
```

Python 3.8+ is supported. `MemoryClient` is asynchronous. `SyncMemoryClient`
supports the core collection, memory, search, correction, procedure, and
ProofLoop workflows; advanced temporal, working-memory, consolidation,
memory-tool, and RL resources are currently async-only.

## Quick start

October 2 follow-up: `proofloop.setup_policy` atomically creates a new
context/schema policy with explicitly declared low-risk exploration; existing
policies are not migrated automatically. `learning_report` reads a bounded,
scoped descriptive report, not proven uplift. `decide_with_advice` reads an
evidence card, invokes the supplied advisor once and logs its actual choice and
probabilities. `decide` accepts bounded `prior_action` / `prior_strength` for one
server-selected decision; this is not outcome evidence. These new helpers and
structured paraphrase matching require the matching October 2 outcome-followup
backend, not merely its database schema; inspect `/v1/release` before use.
Nothing here grants permission to execute. Learning performance and reliable
model compliance with feedback are not established.

Both clients expose `proofloop.register_context_schema`, `context_schema`,
`configure_policy`, `policy_configuration`, `policy_advice` and `action_advice`.
Enroll context before recording decisions. Configuration uses `expected_revision`
for compare-and-swap; do not retry a conflict blindly. Exploration remains an
explicit low-risk opt-in. `action_advice` takes the exact configured description,
policy/action IDs and context, and maps `user_id` to the confidence endpoint's
`end_user_id`. For the complete request shapes, see the
[learning guide](https://www.hebbrix.com/docs/learning).

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
## Native experience workflow (prerelease)

The current source includes `client.experiences`, bounded reflection workers,
separate lesson review/revision and explicit one-use execution admission. These
methods require the matching new backend; the published 2.5.0 release does not
include this extension. The candidate package supplies `hebbrix-reflect --help`.
Importing it does not call a model, approve a lesson or execute a tool.

See `docs/native-experience-operations.md` for role scopes,
uncertain-call recovery, exact-request binding and policy rollback. Do not treat a
lesson, score, review or issued permit as execution permission.
