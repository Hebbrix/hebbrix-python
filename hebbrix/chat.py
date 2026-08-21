"""
Hebbrix Chat Wrapper - 3-Line Integration

The easiest way to add memory-powered conversations to your application.

Example:
    from hebbrix import MemoryChat

    chat = MemoryChat(api_key="mem_sk_...")
    response = chat.send("What's my favorite food?", session_id="user_123")
"""

from typing import Any, Dict, List, Optional

import requests
from hebbrix.client import MemoryClient


class MemoryChat:
    """
    Simple chat interface with automatic memory integration.

    This is the easiest way to use Hebbrix - just 3 lines of code!

    Features:
    - Automatic memory retrieval
    - User profile injection
    - Session management
    - RL-powered personalization
    - OpenAI-compatible responses

    Example:
        ```python
        from hebbrix import MemoryChat

        # Line 1: Initialize
        chat = MemoryChat(api_key="mem_sk_...")

        # Line 2: Send message
        response = chat.send("Hi, remember that I love pizza?", "user_123")

        # Line 3: Get response with memory
        response = chat.send("What's my favorite food?", "user_123")
        print(response)  # "Your favorite food is pizza!"
        ```

    Args:
        api_key: Hebbrix API key
        base_url: API base URL (default: https://api.hebbrix.com)
        model: LLM model to use (default: gpt-5-mini)
        auto_memory: Enable automatic memory retrieval (default: True)
        auto_profile: Enable user profile injection (default: True)
        personalization: Enable RL-powered personalization (default: True)
        learning: Enable RL trajectory logging (default: True)
        prompt_strategy: Prompt template strategy (default: "default")
        memory_limit: Max memories to retrieve per message (default: 10)
        source: Collection source ("app" or "api") for data isolation. Sent as X-Hebbrix-Source header.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.hebbrix.com",
        model: str = "gpt-5-mini",
        auto_memory: bool = True,
        auto_profile: bool = True,
        personalization: bool = True,
        learning: bool = True,
        prompt_strategy: str = "default",
        memory_limit: int = 10,
        source: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt_strategy = prompt_strategy
        self.memory_limit = memory_limit
        self.source = source

        # Feature configuration
        self.features = {
            "memory": auto_memory,
            "user_profile": auto_profile,
            "personalization": personalization,
            "learning": learning,
        }

        # Also create full client for advanced operations
        self.client = MemoryClient(api_key=api_key, base_url=base_url, source=source)

    def send(
        self,
        message: str,
        session_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a message and get a response with automatic memory integration.

        This is the main method - just call it and Hebbrix handles everything!

        Args:
            message: Your message
            session_id: Session identifier (user ID or conversation ID)
            temperature: Response randomness (0-2, default: 0.7)
            max_tokens: Maximum response length (default: None)

        Returns:
            Assistant's response as a string

        Example:
            response = chat.send("What did I tell you earlier?", "user_123")
        """
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message}],
            "session_id": session_id,
            "features": self.features,
            "prompt_strategy": self.prompt_strategy,
            "memory_limit": self.memory_limit,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.source:
            headers["X-Hebbrix-Source"] = self.source

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    def send_with_context(
        self,
        message: str,
        session_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a message and get full response with memory context.

        Use this when you want to see which memories were used.

        Args:
            message: Your message
            session_id: Session identifier
            temperature: Response randomness (0-2, default: 0.7)
            max_tokens: Maximum response length (default: None)

        Returns:
            Full response dict with memory context

        Example:
            result = chat.send_with_context("What's my name?", "user_123")
            print(result["message"])  # Assistant's response
            print(result["memory_context"])  # Which memories were used
        """
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message}],
            "session_id": session_id,
            "features": self.features,
            "prompt_strategy": self.prompt_strategy,
            "memory_limit": self.memory_limit,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.source:
            headers["X-Hebbrix-Source"] = self.source

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()

        return {
            "message": data["choices"][0]["message"]["content"],
            "memory_context": data["memory_context"],
            "usage": data["usage"],
            "model": data["model"],
        }

    def configure_features(
        self,
        auto_memory: Optional[bool] = None,
        auto_profile: Optional[bool] = None,
        personalization: Optional[bool] = None,
        learning: Optional[bool] = None,
    ) -> None:
        """
        Configure features on the fly.

        Args:
            auto_memory: Enable/disable automatic memory retrieval
            auto_profile: Enable/disable user profile injection
            personalization: Enable/disable RL personalization
            learning: Enable/disable RL learning
        """
        if auto_memory is not None:
            self.features["memory"] = auto_memory
        if auto_profile is not None:
            self.features["user_profile"] = auto_profile
        if personalization is not None:
            self.features["personalization"] = personalization
        if learning is not None:
            self.features["learning"] = learning

    def set_model(self, model: str) -> None:
        """
        Change the LLM model.

        Args:
            model: Model name (e.g., "gpt-5-mini", "gpt-5.2", "claude-3-sonnet")
        """
        self.model = model

    def set_strategy(self, strategy: str) -> None:
        """
        Change the prompt strategy.

        Args:
            strategy: Strategy name ("default", "concise", "detailed")
        """
        self.prompt_strategy = strategy

    def list_sessions(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        List all chat sessions.

        Args:
            active_only: Only return active sessions

        Returns:
            List of session dicts
        """
        url = f"{self.base_url}/v1/chat/sessions"
        params = {"active_only": active_only}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()

        return response.json()["sessions"]

    def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        Get information about a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Session info and statistics
        """
        url = f"{self.base_url}/v1/chat/sessions/{session_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return response.json()

    def delete_session(self, session_id: str) -> None:
        """
        Delete a chat session.

        Args:
            session_id: Session identifier
        """
        url = f"{self.base_url}/v1/chat/sessions/{session_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        response = requests.delete(url, headers=headers)
        response.raise_for_status()

    # Convenience methods for memory operations
    # These use synchronous requests.post() (same as send/send_with_context)
    # instead of the async MemoryClient to avoid coroutine issues.
    def add_memory(
        self, content: str, collection_id: str, importance: float = 0.5
    ) -> Dict[str, Any]:
        """
        Add a memory manually.

        Args:
            content: Memory content
            collection_id: Collection ID
            importance: Memory importance (0-1)

        Returns:
            Created memory dict
        """
        url = f"{self.base_url}/v1/memories"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "content": content,
            "collection_id": collection_id,
            "importance": importance,
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    def search_memories(
        self, query: str, collection_id: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search memories manually.

        Args:
            query: Search query
            collection_id: Optional collection filter
            limit: Number of results

        Returns:
            List of memory dicts
        """
        url = f"{self.base_url}/v1/search"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "query": query,
            "limit": limit,
        }
        if collection_id:
            payload["collection_id"] = collection_id

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get("results", [])


# Convenience function for even simpler usage
def quick_chat(api_key: str, message: str, session_id: str) -> str:
    """
    The absolute simplest way to use Hebbrix - single function call.

    Args:
        api_key: Hebbrix API key
        message: Your message
        session_id: Session identifier

    Returns:
        Assistant's response

    Example:
        from hebbrix.chat import quick_chat

        response = quick_chat(
            api_key="mem_sk_...",
            message="What's my favorite color?",
            session_id="user_123"
        )
    """
    chat = MemoryChat(api_key=api_key)
    return chat.send(message, session_id)
