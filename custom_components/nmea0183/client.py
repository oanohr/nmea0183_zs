"""Asynchronous NMEA 0183 TCP client."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
import logging

import pynmea2

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
RECONNECT_DELAY = 5


class State(Enum):
    """Connection state of the client."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class Nmea0183TcpClient:
    """Reads NMEA 0183 sentences from a plain TCP stream and reconnects on failure."""

    def __init__(
        self,
        host: str,
        port: int,
        include_sentences: list[str] | None = None,
        exclude_sentences: list[str] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._include = set(include_sentences or [])
        self._exclude = set(exclude_sentences or [])
        self._receive_callback: Callable[[pynmea2.NMEASentence], Awaitable[None]] | None = None
        self._status_callback: Callable[[State], Awaitable[None]] | None = None
        self._stop = asyncio.Event()

    def set_receive_callback(
        self, callback: Callable[[pynmea2.NMEASentence], Awaitable[None]]
    ) -> None:
        self._receive_callback = callback

    def set_status_callback(self, callback: Callable[[State], Awaitable[None]]) -> None:
        self._status_callback = callback

    def stop(self) -> None:
        """Ask run() to return."""
        self._stop.set()

    def parse_line(self, line: str) -> pynmea2.NMEASentence | None:
        """Parse one line. Returns None for invalid, unsupported or filtered sentences."""
        line = line.strip()
        if not line:
            return None
        try:
            msg = pynmea2.parse(line, check=True)
        except pynmea2.ParseError as err:
            _LOGGER.debug("Ignoring line %r: %s", line, err)
            return None

        sentence_type = getattr(msg, "sentence_type", None)
        if sentence_type is None:  # proprietary sentences have no talker/type
            return None
        if self._include and sentence_type not in self._include:
            return None
        if sentence_type in self._exclude:
            return None
        return msg

    async def _set_state(self, state: State) -> None:
        if self._status_callback is not None:
            await self._status_callback(state)

    async def run(self) -> None:
        """Connect, read until stopped, reconnecting after errors."""
        while not self._stop.is_set():
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.TimeoutError, ValueError) as err:
                _LOGGER.warning(
                    "NMEA 0183 connection to %s:%s failed: %s", self._host, self._port, err
                )
            except Exception:  # noqa: BLE001 - keep the client alive
                _LOGGER.exception("Unexpected error in NMEA 0183 client")

            await self._set_state(State.DISCONNECTED)
            try:
                await asyncio.wait_for(self._stop.wait(), RECONNECT_DELAY)
            except asyncio.TimeoutError:
                pass

    async def _session(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), CONNECT_TIMEOUT
        )
        _LOGGER.info("Connected to %s:%s", self._host, self._port)
        await self._set_state(State.CONNECTED)
        try:
            while not self._stop.is_set():
                raw = await asyncio.wait_for(reader.readline(), READ_TIMEOUT)
                if not raw:
                    raise ConnectionError("connection closed by receiver")
                msg = self.parse_line(raw.decode("ascii", errors="replace"))
                if msg is not None and self._receive_callback is not None:
                    await self._receive_callback(msg)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
