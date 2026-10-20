"""A fake NMEA 0183 TCP server for end-to-end tests."""
from __future__ import annotations

import asyncio
import random

from .test_sentences import GGA


class FakeNmeaServer:
    """Accepts clients and sends sentences on demand or at a fixed cadence."""

    def __init__(self) -> None:
        self.port: int = 0
        self.connections = 0
        self._server: asyncio.Server | None = None
        self._writers: list[asyncio.StreamWriter] = []
        self._cadence_task: asyncio.Task | None = None

    async def start(self, port: int = 0) -> None:
        self._server = await asyncio.start_server(self._on_client, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _on_client(self, reader, writer) -> None:
        self.connections += 1
        self._writers.append(writer)

    async def send(self, line: str = GGA) -> None:
        for writer in list(self._writers):
            writer.write(f"{line}\r\n".encode())
            await writer.drain()

    def start_cadence(self, interval: float, jitter: float = 0.0, line: str = GGA) -> None:
        """Send `line` every `interval` seconds, each delay varied by +-jitter (fraction)."""

        async def run() -> None:
            while True:
                await self.send(line)
                await asyncio.sleep(interval * (1 + random.uniform(-jitter, jitter)))

        self.stop_cadence()
        self._cadence_task = asyncio.create_task(run())

    def stop_cadence(self) -> None:
        if self._cadence_task is not None:
            self._cadence_task.cancel()
            self._cadence_task = None

    def drop_clients(self) -> None:
        """Close all client connections (EOF for the reader)."""
        for writer in self._writers:
            writer.close()
        self._writers.clear()

    async def stop(self) -> None:
        self.stop_cadence()
        self.drop_clients()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
