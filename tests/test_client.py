"""Tests for the NMEA 0183 TCP client against a local TCP server."""
import asyncio

from custom_components.nmea0183.client import Nmea0183TcpClient, State
from .test_sentences import GGA, RMC


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
