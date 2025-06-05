import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any

class AsyncMCPTransport(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish async connection to MCP server"""
        pass

    @abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send async message to server"""
        pass

    @abstractmethod
    async def receive_messages(self) -> AsyncIterator[Dict[str, Any]]:
        """Async generator for incoming messages"""
        # This is an async generator, so it should yield results.
        # For the abstract method, we can make it pass, or raise NotImplementedError.
        # Given it's an async generator, it must yield. An empty generator is fine.
        if False: # Ensure this is recognized as a generator
            yield {}

    @abstractmethod
    async def disconnect(self) -> None:
        """Graceful async disconnection"""
        pass

# Concrete implementations for stdio, sse, streamable_http will follow.
