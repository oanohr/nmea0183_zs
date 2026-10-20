"""Tests for the NMEA 0183 TCP client against a local TCP server."""
import asyncio
import logging
from unittest.mock import patch

import pytest

from custom_components.nmea0183.client import LOG_INTERVAL, Nmea0183TcpClient, State
from .test_sentences import GGA, RMC

pytestmark = pytest.mark.usefixtures("socket_enabled")


async def test_client_receives_sentences_and_reports_state():
    async def handle(reader, writer):
        writer.write(f"garbage\r\n{GGA}\r\n{RMC}\r\n".encode())
        await writer.drain()
        await asyncio.sleep(0.2)
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    received, states = [], []
    client = Nmea0183TcpClient("127.0.0.1", port)

    async def on_msg(msg):
        received.append(msg.sentence_type)
        if len(received) == 2:
            client.stop()

    async def on_state(state):
        states.append(state)

    client.set_receive_callback(on_msg)
    client.set_status_callback(on_state)

    async with server:
        await asyncio.wait_for(client.run(), 10)

    assert received == ["GGA", "RMC"]
    assert states[0] == State.CONNECTED
    assert states[-1] == State.DISCONNECTED


async def test_client_does_not_time_out_while_sentences_arrive_in_time():
    """Sentences arriving inside the read timeout keep the connection (the 30 s GGA case)."""

    async def handle(reader, writer):
        for _ in range(4):
            writer.write(f"{GGA}\r\n".encode())
            await writer.drain()
            await asyncio.sleep(0.2)
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    received, states = [], []
    client = Nmea0183TcpClient("127.0.0.1", port, read_timeout=0.5)

    async def on_msg(msg):
        received.append(msg)
        if len(received) == 4:
            client.stop()

    async def on_state(state):
        states.append(state)

    client.set_receive_callback(on_msg)
    client.set_status_callback(on_state)
    async with server:
        await asyncio.wait_for(client.run(), 10)

    # CONNECTED once, then DISCONNECTED only after the stream ended
    assert states == [State.CONNECTED, State.DISCONNECTED]


async def test_client_reconnects_after_silence_longer_than_read_timeout():
    connections = []

    async def handle(reader, writer):
        connections.append(writer)  # accept and stay silent

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    states = []
    client = Nmea0183TcpClient("127.0.0.1", port, read_timeout=0.2)

    async def on_state(state):
        states.append(state)
        if len(connections) == 2:
            client.stop()

    client.set_status_callback(on_state)
    with patch("custom_components.nmea0183.client.RECONNECT_DELAY", 0.05):
        async with server:
            try:
                await asyncio.wait_for(client.run(), 10)
            finally:
                for writer in connections:  # wait_closed() needs all connections closed
                    writer.close()

    assert len(connections) >= 2
    assert State.DISCONNECTED in states


# --- malformed input, line limits and log noise (#10) ---

def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


async def _serve_and_collect(chunks, *, expect, read_timeout=5.0):
    """Send `chunks` (bytes, with optional pauses as floats) and collect accepted sentences."""
    connections = []

    async def handle(reader, writer):
        connections.append(writer)
        for chunk in chunks:
            if isinstance(chunk, float):
                await asyncio.sleep(chunk)
            else:
                writer.write(chunk)
                await writer.drain()
        await asyncio.sleep(5)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    received = []
    client = Nmea0183TcpClient("127.0.0.1", port, read_timeout=read_timeout)

    async def on_msg(msg):
        received.append(msg.sentence_type)
        if len(received) == expect:
            client.stop()

    client.set_receive_callback(on_msg)
    async with server:
        try:
            await asyncio.wait_for(client.run(), 10)
        finally:
            for writer in connections:
                writer.close()
    return client, received, len(connections)


async def test_malformed_lines_are_counted_and_do_not_stop_the_stream():
    no_checksum = GGA.split("*")[0].encode() + b"\r\n"
    bad_checksum = GGA[:-2].encode() + b"00\r\n"
    client, received, connections = await _serve_and_collect(
        [
            b"garbage\r\n",
            no_checksum,
            bad_checksum,
            b"\xff\xfe\x00\x01 binary \x80\r\n",
            f"{GGA}\r\n".encode(),
        ],
        expect=1,
    )
    assert received == ["GGA"]
    assert connections == 1  # no reconnect because of bad lines
    stats = client.stats
    assert stats.lines == 5
    assert stats.accepted == 1
    assert stats.checksum_rejected >= 2  # missing and wrong checksum
    assert stats.malformed + stats.checksum_rejected == 4
    assert stats.last_accepted is not None


async def test_oversized_line_is_dropped_without_reconnecting():
    client, received, connections = await _serve_and_collect(
        [b"A" * 10_000 + b"\r\n", f"{GGA}\r\n".encode()], expect=1
    )
    assert received == ["GGA"]
    assert connections == 1
    assert client.stats.oversized >= 1
    assert client.stats.accepted == 1


async def test_endless_line_without_newline_does_not_stop_recovery():
    client, received, connections = await _serve_and_collect(
        [b"B" * 50_000, f"\r\n{GGA}\r\n".encode()], expect=1
    )
    assert received == ["GGA"]
    assert connections == 1
    assert client.stats.oversized >= 1


async def test_sentence_split_over_several_tcp_frames_is_reassembled():
    line = f"{GGA}\r\n".encode()
    client, received, _ = await _serve_and_collect(
        [line[:20], 0.05, line[20:45], 0.05, line[45:]], expect=1
    )
    assert received == ["GGA"]
    assert client.stats.accepted == 1
    assert client.stats.malformed == client.stats.checksum_rejected == 0


def test_rejected_lines_warn_once_per_interval_and_without_the_content(caplog):
    now = [1000.0]
    client = Nmea0183TcpClient("h", 1, clock=lambda: now[0])
    secret = "SECRETPAYLOAD"
    with caplog.at_level(logging.INFO):
        for _ in range(200):
            assert client.parse_line(secret) is None
        assert len(_warnings(caplog)) == 1
        assert secret not in _warnings(caplog)[0].getMessage()

        now[0] += LOG_INTERVAL - 1
        client.parse_line(secret)
        assert len(_warnings(caplog)) == 1  # still inside the interval

        now[0] += 1
        client.parse_line(secret)
        assert len(_warnings(caplog)) == 2
    assert client.stats.malformed == 202


async def test_receiver_down_logs_one_warning_and_recovery_is_reported(caplog):
    connections = []

    async def handle(reader, writer):
        connections.append(writer)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    real_open_connection = asyncio.open_connection
    attempts = []

    async def refuse_six_times(*args, **kwargs):
        # A refused connection takes seconds on some platforms: fail instantly instead
        attempts.append(1)
        if len(attempts) <= 6:
            raise ConnectionRefusedError("receiver down")
        return await real_open_connection(*args, **kwargs)

    client = Nmea0183TcpClient("127.0.0.1", port, read_timeout=5)

    async def on_state(state):
        if state == State.CONNECTED:
            client.stop()

    client.set_status_callback(on_state)
    with caplog.at_level(logging.DEBUG), patch(
        "custom_components.nmea0183.client.RECONNECT_DELAY", 0.02
    ), patch("custom_components.nmea0183.client.asyncio.open_connection", refuse_six_times):
        async with server:
            try:
                await asyncio.wait_for(client.run(), 10)
            finally:
                for writer in connections:
                    writer.close()

    assert len(attempts) == 7
    assert len(_warnings(caplog)) == 1
    assert any(
        "failed attempt" in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO
    )


async def test_receiver_that_keeps_dropping_logs_one_warning(caplog):
    connections = []

    async def handle(reader, writer):
        connections.append(1)
        writer.close()  # EOF straight away

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = Nmea0183TcpClient("127.0.0.1", port, read_timeout=5)

    async def on_state(state):
        if len(connections) >= 5:
            client.stop()

    client.set_status_callback(on_state)
    with caplog.at_level(logging.DEBUG), patch(
        "custom_components.nmea0183.client.RECONNECT_DELAY", 0.02
    ):
        async with server:
            await asyncio.wait_for(client.run(), 10)

    assert len(connections) >= 5
    assert len(_warnings(caplog)) == 1
