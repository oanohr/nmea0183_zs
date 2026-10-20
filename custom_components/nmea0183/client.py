"""Asynchronous NMEA 0183 TCP client."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from enum import Enum
import logging
import time

import pynmea2

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 120
RECONNECT_DELAY = 5
# NMEA 0183 sentences are at most 82 characters; proprietary ones are longer, so allow margin
MAX_LINE_LENGTH = 1024
# At most one warning per this many seconds about rejected lines or a failing connection
LOG_INTERVAL = 300


class State(Enum):
    """Connection state of the client."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


@dataclass
class LineStats:
    """What the receiver has sent, counted per kind. Separate from accepted messages."""

    lines: int = 0  # non-empty lines received
    accepted: int = 0  # valid checksum and parsed (before the sentence filter)
    checksum_rejected: int = 0  # wrong or missing checksum
    malformed: int = 0  # not NMEA at all
    oversized: int = 0  # longer than MAX_LINE_LENGTH
    last_accepted: float | None = None  # clock() of the last accepted line

    def as_dict(self) -> dict:
        return asdict(self)


class Nmea0183TcpClient:
    """Reads NMEA 0183 sentences from a plain TCP stream and reconnects on failure."""

    def __init__(
        self,
        host: str,
        port: int,
        include_sentences: list[str] | None = None,
        exclude_sentences: list[str] | None = None,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._host = host
        self._port = port
        self._include = set(include_sentences or [])
        self._exclude = set(exclude_sentences or [])
        self._receive_callback: Callable[[pynmea2.NMEASentence], Awaitable[None]] | None = None
        self._status_callback: Callable[[State], Awaitable[None]] | None = None
        self._read_timeout = read_timeout
        self._stop = asyncio.Event()
        self._clock = clock
        self.stats = LineStats()
        self._rejected_since_log = 0
        self._last_reject_log: float | None = None
        self._failed_attempts = 0
        self._last_failure_log: float | None = None

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
        self.stats.lines += 1
        try:
            msg = pynmea2.parse(line, check=True)
        except pynmea2.ChecksumError:
            self.stats.checksum_rejected += 1
            self._rejected(line, "checksum")
            return None
        except (ValueError, IndexError):  # pynmea2.ParseError is a ValueError
            self.stats.malformed += 1
            self._rejected(line, "malformed")
            return None
        self.stats.accepted += 1
        self.stats.last_accepted = self._clock()

        sentence_type = getattr(msg, "sentence_type", None)
        if sentence_type is None:  # proprietary sentences have no talker/type
            return None
        if self._include and sentence_type not in self._include:
            return None
        if sentence_type in self._exclude:
            return None
        return msg

    def _rejected(self, line: str, kind: str) -> None:
        """Count a rejected line; warn at most once per LOG_INTERVAL, without the content."""
        _LOGGER.debug("Ignoring %s line: %.80r", kind, line)
        self._rejected_since_log += 1
        now = self._clock()
        if self._last_reject_log is None or now - self._last_reject_log >= LOG_INTERVAL:
            _LOGGER.warning(
                "NMEA 0183 from %s:%s: %d line(s) rejected since the last report "
                "(%d checksum, %d malformed, %d oversized in total). "
                "Further reports at most every %d s.",
                self._host,
                self._port,
                self._rejected_since_log,
                self.stats.checksum_rejected,
                self.stats.malformed,
                self.stats.oversized,
                LOG_INTERVAL,
            )
            self._rejected_since_log = 0
            self._last_reject_log = now

    def _connection_failed(self, err: Exception | str) -> None:
        """Warn about the first failure, then at most once per LOG_INTERVAL."""
        self._failed_attempts += 1
        now = self._clock()
        if self._last_failure_log is None or now - self._last_failure_log >= LOG_INTERVAL:
            _LOGGER.warning(
                "NMEA 0183 connection to %s:%s failed (%d attempt(s) so far): %s",
                self._host,
                self._port,
                self._failed_attempts,
                err,
            )
            self._last_failure_log = now
        else:
            _LOGGER.debug("NMEA 0183 connection failed again: %s", err)

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
                self._connection_failed(err)
            except Exception as err:  # noqa: BLE001 - keep the client alive
                self._connection_failed(err)
                _LOGGER.debug("Unexpected error in NMEA 0183 client", exc_info=True)

            await self._set_state(State.DISCONNECTED)
            try:
                await asyncio.wait_for(self._stop.wait(), RECONNECT_DELAY)
            except asyncio.TimeoutError:
                pass

    async def _session(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port, limit=MAX_LINE_LENGTH),
            CONNECT_TIMEOUT,
        )
        if self._failed_attempts:
            _LOGGER.info(
                "Connected to %s:%s after %d failed attempt(s)",
                self._host,
                self._port,
                self._failed_attempts,
            )
        else:
            _LOGGER.info("Connected to %s:%s", self._host, self._port)
        self._failed_attempts = 0
        await self._set_state(State.CONNECTED)
        try:
            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(reader.readline(), self._read_timeout)
                except ValueError:
                    # Line longer than MAX_LINE_LENGTH: asyncio dropped what it had
                    # buffered. Count it and read on; the session is still fine.
                    self.stats.lines += 1
                    self.stats.oversized += 1
                    self._rejected(f"<over {MAX_LINE_LENGTH} bytes>", "oversized")
                    continue
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
