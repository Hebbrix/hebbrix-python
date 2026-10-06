# Hebbrix Python SDK

Typed Python client for Hebbrix memory, retrieval, and outcome-learning APIs.

The current stable package is **2.6.2**. Start with memory storage and search, or
the three-call outcome-learning workflow below. Advanced evidence and execution
permission transports are opt-in; installing the SDK never permits an action.

## Install

```bash
pip install hebbrix==2.6.2
```

Python 3.8+ is supported. `MemoryClient` is asynchronous. `SyncMemoryClient`
supports the core collection, memory, search, correction, procedure, and
outcome-learning workflows; advanced temporal, working-memory, consolidation,
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

## Learn from outcomes in three calls

Use server-side selection when Hebbrix should choose. Read-only advice is for a
caller that intentionally chooses outside Hebbrix; an LLM can ignore that advice.
Configure a new policy once, request a decision, then report its actual result:

```python
await client.proofloop.setup_policy(
    "support.reply.v1", user_id="customer-42",
    context_schema={"version": "v1", "fields": {
        "issue": {"values": ["delivery", "billing"], "required": True}
    }},
    actions={
        "explain": {"description": "Explain the delivery status", "target": "ticket",
                    "risk_tier": "low", "exploration_allowed": True},
        "review": {"description": "Request a support review", "target": "ticket",
                   "risk_tier": "low", "exploration_allowed": True},
    },
    configuration={"strategy": "posterior_sampling"},
)
decision = await client.proofloop.decide(
    policy_key="support.reply.v1", user_id="customer-42", mode="auto",
    context={"issue": "delivery"},
    candidates=[{"action_key": "explain"}, {"action_key": "review"}],
    idempotency_key="ticket-42-decision",
)
# Your application checks permission and performs the action separately.
# Here success is the actual result supplied by that application, not a prediction.
await client.proofloop.record_outcome(
    decision["decision_id"], success=success,
    idempotency_key="ticket-42-result",
)
```

`success` must come from your application or an independently authorized
verifier. Do not report the recommendation itself as a successful execution.
Keep action identities and required context stable. Use a new policy/version
when changing what an action or outcome means. See the
[recommended defaults](https://hebbrix.com/docs/learning).

## Advice and integration boundaries

`proofloop.action_advice(...)` reads the exact configured action and context.
The canonical `gate` is `ASK`, `REVIEW`, `ACT`, or `BLOCK`. `BLOCK` dominates;
`ACT` is advice, not permission. Apply your own current authorization and human
approval policy before executing any tool. Do not infer permission from a score.

Version 2.6.2 adds compact advice, batch, and explicit confirmation helpers.
They require matching Round9 server routes. Compact views retain scope and safety
caveats; complete receipts remain on the server.

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

- [Documentation](https://hebbrix.com/docs)
- [API reference](https://api.hebbrix.com/docs)
- [PyPI files](https://pypi.org/project/hebbrix/#files)
- [Support](https://www.hebbrix.com/contact)

## License

MIT. See `LICENSE` in the distribution.
## Advanced evidence workflows

The current source includes `client.experiences`, bounded reflection workers,
separate lesson review/revision and explicit one-use execution admission. These
methods require the server's published compatibility contract and separately
scoped credentials. The package supplies `hebbrix-reflect --help`.
Importing it does not call a model, approve a lesson or execute a tool.

See the [documentation](https://hebbrix.com/docs) for role scopes,
uncertain-call recovery, exact-request binding and policy rollback. Do not treat a
lesson, score, review or issued permit as execution permission.

## Stability

Stable SDK versions follow semantic versioning. Patch updates correct defects;
new optional fields and methods are additive. Existing required context, action
identity, owner scope, and historical outcomes are not silently rewritten.
Experimental APIs are marked separately. Security and correctness guards may
be tightened immediately; migrations and other incompatible changes must be
documented with their supported replacement. Read [CHANGELOG.md](CHANGELOG.md)
before upgrading and pin versions in production. Release cadence is not a
performance, compliance, or reliability guarantee.
