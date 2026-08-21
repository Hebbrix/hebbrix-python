# Hebbrix Python SDK

[![PyPI version](https://img.shields.io/pypi/v/hebbrix.svg)](https://pypi.org/project/hebbrix/)
[![Python versions](https://img.shields.io/pypi/pyversions/hebbrix.svg)](https://pypi.org/project/hebbrix/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Official Python SDK for the Hebbrix api - **the only memory API with Reinforcement Learning**.

## 🚀 Features

- ✅ **Complete API Coverage** - All 50+ endpoints supported
- ✅ **Reinforcement Learning** - Train AI agents to optimize memory operations
- ✅ **Temporal Knowledge Graphs** - Track facts over time with bi-temporal model
- ✅ **Procedural Memory** - Store and execute learned skills
- ✅ **Working Memory** - Short-term context buffer for conversations
- ✅ **Memory Consolidation** - Automatic compression of episodic memories
- ✅ **ProofLoop** - Learn from outcomes with automatic, verifiable evidence receipts
- ✅ **Async/Await** - Full async support with httpx
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
        content="User prefers dark mode and loves Python",
        importance=0.9
    )

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
