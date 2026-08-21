"""
Hebbrix Python SDK - Advanced Memory API for AI Agents

A modern, async-first Python SDK for the Hebbrix Memory API.
The only memory API with Reinforcement Learning for AI agents.

Quick Start:

    from hebbrix import MemoryClient, MemoryChat

    # Option 1: Simple 3-line chat integration
    chat = MemoryChat(api_key="hbx_...")
    response = chat.send("Remember I love Python!", "user_123")
    response = chat.send("What language do I like?", "user_123")

    # Option 2: Full async API client
    async with MemoryClient(api_key="hbx_...") as client:
        # Create collection
        collection = await client.collections.create(name="My Agent")

        # Store memory
        memory = await client.memories.create(
            collection_id=collection["id"],
            content="Important information"
        )

        # Search with hybrid vector + BM25 + graph
        results = await client.search(query="What was important?", limit=5)

        # AI-powered reasoning over memories
        answer = await client.reason(query="Explain what I learned")

Features:
- ✅ Reinforcement Learning for memory optimization
- ✅ Temporal Knowledge Graphs with bi-temporal model
- ✅ Procedural Memory (skills and learned behaviors)
- ✅ Working Memory (short-term context buffer)
- ✅ Memory Consolidation (automatic compression)
- ✅ 6-layer Hybrid Search (Vector + BM25 + KG + Decay + AI + RL)
- ✅ Complete async/await support
- ✅ Type hints throughout
"""

__version__ = "2.2.0"
__author__ = "Hebbrix Team"
__license__ = "MIT"

from hebbrix.client import MemoryClient
from hebbrix.chat import MemoryChat
from hebbrix.exceptions import (
    HebbrixError,
    AuthenticationError,
    ValidationError,
    NotFoundError,
    RateLimitError,
    ServerError,
)


__all__ = [
    "MemoryClient",
    "MemoryChat",
    "HebbrixError",
    "AuthenticationError",
    "ValidationError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
]
