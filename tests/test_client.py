"""Tests for the NMEA 0183 TCP client against a local TCP server."""
import asyncio
from unittest.mock import patch

import pytest

from custom_components.nmea0183.client import Nmea0183TcpClient, State
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
