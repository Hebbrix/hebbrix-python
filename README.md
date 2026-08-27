# Hebbrix Python SDK

[![PyPI version](https://img.shields.io/pypi/v/hebbrix.svg)](https://pypi.org/project/hebbrix/)
[![Python versions](https://img.shields.io/pypi/pyversions/hebbrix.svg)](https://pypi.org/project/hebbrix/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Official Python SDK for the Hebbrix api - **the only memory API with Reinforcement Learning**.

## 🚀 Features

- ✅ **Core API Coverage** - Typed resources for memories, search, and ProofLoop
- ✅ **Reinforcement Learning** - Train AI agents to optimize memory operations
- ✅ **Temporal Knowledge Graphs** - Track facts over time with bi-temporal model
- ✅ **Procedural Memory** - Store and execute learned skills
- ✅ **Working Memory** - Short-term context buffer for conversations
- ✅ **Memory Consolidation** - Automatic compression of episodic memories
- ✅ **ProofLoop** - Learn from outcomes with automatic, verifiable evidence receipts
- ✅ **Sync + Async** - Equivalent core memory and ProofLoop workflows
- ✅ **Type Hints** - Complete type annotations
- ✅ **Clean API** - Pythonic, intuitive interface

## 📦 Installation

```bash
pip install hebbrix
```

## 🔥 Quick Start

```python
import asyncio
from hebbrix import MemoryClient

async def main():
    # Initialize client
    client = MemoryClient(api_key="mem_sk_your_api_key")

    # Create a collection
    collection = await client.collections.create(
        name="My AI Agent",
        description="Personal memory for my chatbot"
    )

    # Store a memory
    memory = await client.memories.create(
        collection_id=collection["id"],
        user_id="customer-7",
        agent_id="support-agent",
        content="User prefers dark mode and loves Python",
        importance=0.9,
        wait_for_index=True,
    )

    # wait_for_index=True polls the returned memory status through the SDK.
    # It returns only when searchable=true, raises on terminal failure, and
    # raises TimeoutError if the caller's readiness deadline expires.

    # Batch contract: a successful synchronous return means every accepted item
    # is searchable. A bounded server timeout raises explicitly and is safe to
    # retry with the same idempotency key; it is never a successful 202.
    batch = await client.memories.create_batch(
        [{"content": "First fact"}, {"content": "Second fact"}],
        collection_id=collection["id"],
        wait_for_index=True,
        idempotency_key="import-42",
    )
    # For wait_for_index=False receipts:
    # batch = await client.memories.wait_batch_until_searchable(batch)

    # Search memories
    results = await client.search(
        query="What programming language does user like?",
        collection_id=collection["id"],
        limit=5
    )

    print(results)

    # Close client
    await client.close()

asyncio.run(main())
```

Blocking applications can use the same create/search/ProofLoop fields:

```python
from hebbrix import SyncMemoryClient

with SyncMemoryClient(api_key="mem_sk_your_api_key") as client:
    collection = client.collections.create(name="My Agent")
    client.memories.create(
        collection_id=collection["id"],
        user_id="customer-7",
        content="User prefers concise answers",
        wait_for_index=True,
    )
    results = client.search(
        "How should answers be formatted?",
        collection_id=collection["id"],
        user_id="customer-7",
    )
```

## ProofLoop: search → decision → outcome → proof

```python
search = await client.search_with_proof(
    "What should the agent do next?",
    collection_id="collection-42",
    user_id="customer-7",
)
decision = await client.proofloop.decide(
    policy_key="agent.next_action",
    candidates=[{"action_key": "act"}, {"action_key": "ask"}],
    collection_id="collection-42",
    user_id="customer-7",
    proof_context=search["proof_context"],
)
await client.proofloop.record_outcome(
    decision["decision_id"], success=True, idempotency_key="run-123-result"
)
proof = await client.proofloop.proof(decision["decision_id"])
```

## 📚 Complete Documentation

Visit https://docs.hebbrix.com for full documentation.

## 🔗 Links

- **Documentation**: https://docs.hebbrix.com
- **API Reference**: https://api.hebbrix.com/docs
- **GitHub**: https://github.com/hebbrix/hebbrix
- **Examples**: https://github.com/hebbrix/examples

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

---

**Built with ❤️ by the Hebbrix team**
