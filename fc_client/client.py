import asyncio
import traceback
from typing import Optional, Dict, Callable, Awaitable
from . import protocol
from . import handlers

class FreeCivClient:
    reader: Optional[asyncio.StreamReader]
    writer: Optional[asyncio.StreamWriter]
    _shutdown_event: Optional[asyncio.Event]
    _join_successful: asyncio.Event
    _packet_handlers: Dict[int, Callable[['FreeCivClient', bytes], Awaitable[None]]]
    _packet_reader_task: Optional[asyncio.Task]

    def __init__(self):
        self.reader = None
        self.writer = None
        self._shutdown_event = None
        self._join_successful = asyncio.Event()
        self._packet_handlers = {}
        self._packet_reader_task = None

        # Register packet handlers
        self.register_handler(protocol.PACKET_PROCESSING_STARTED, handlers.handle_processing_started)
        self.register_handler(protocol.PACKET_PROCESSING_FINISHED, handlers.handle_processing_finished)
        self.register_handler(protocol.PACKET_SERVER_JOIN_REPLY, handlers.handle_server_join_reply)

    def register_handler(self, packet_type: int, handler: Callable[['FreeCivClient', bytes], Awaitable[None]]) -> None:
        """
        Register a packet handler function for a specific packet type.

        Args:
            packet_type: The packet type number to handle
            handler: Async function that takes (client, payload) and processes the packet
        """
        self._packet_handlers[packet_type] = handler

    async def connect(self, host: str, port: int) -> bool:
        """
        Connect to the FreeCiv server.

        Args:
            host: Server hostname or IP address
            port: Server port number

        Returns:
            True if connection successful
        """
        self.reader, self.writer = await asyncio.open_connection(host, port)
        print(f"Connected to {host}:{port}")
        return True

    async def send_join_request(self, username: str) -> None:
        """
        Send a JOIN_REQ packet to the server.

        Does not wait for the reply - that will be handled by the event loop.

        Args:
            username: Username to join as
        """
        if not self.reader or not self.writer:
            print("Error: Not connected to server")
            return

        # Encode and send JOIN_REQ packet
        join_req_packet = protocol.encode_server_join_req(username)
        self.writer.write(join_req_packet)
        await self.writer.drain()
        print(f"Sent JOIN_REQ for user '{username}'")

    async def start_packet_reader(self, shutdown_event: asyncio.Event) -> None:
        """
        Start the packet reading loop in the background.

        Args:
            shutdown_event: Event that will be set to trigger shutdown
        """
        self._shutdown_event = shutdown_event
        self._packet_reader_task = asyncio.create_task(self._packet_reading_loop())

    async def _packet_reading_loop(self) -> None:
        """
        Main event loop that continuously reads and dispatches packets.

        Runs until shutdown event is set or a connection error occurs.
        """
        try:
            while not self._shutdown_event.is_set():
                # Read next packet
                packet_type, payload = await protocol.read_packet(self.reader)
                print(f"Received packet type: {packet_type}")

                # Dispatch to handler
                await self._dispatch_packet(packet_type, payload)

        except asyncio.IncompleteReadError:
            print("Connection closed by server")
            self._shutdown_event.set()
        except ConnectionError as e:
            print(f"Connection error: {e}")
            self._shutdown_event.set()
        except Exception as e:
            print(f"Unexpected error in packet reading loop: {e}")
            traceback.print_exc()
            self._shutdown_event.set()

    async def _dispatch_packet(self, packet_type: int, payload: bytes) -> None:
        """
        Dispatch a packet to its registered handler.

        If no handler is registered, call the unknown packet handler.

        Args:
            packet_type: The packet type number
            payload: The packet payload bytes
        """
        try:
            # Look up handler
            handler = self._packet_handlers.get(packet_type)

            if handler:
                # Call the registered handler
                await handler(self, payload)
            else:
                # Call unknown packet handler
                await handlers.handle_unknown_packet(self, packet_type, payload)

        except Exception as e:
            print(f"Error in packet handler for type {packet_type}: {e}")
            traceback.print_exc()
            self._shutdown_event.set()

    async def wait_for_join(self, timeout: float = 10.0) -> bool:
        """
        Wait for the join successful event.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if join was successful, False if timeout occurred
        """
        try:
            await asyncio.wait_for(self._join_successful.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def stop_and_disconnect(self) -> None:
        """
        Stop the packet reader task and disconnect from the server.
        """
        # Cancel packet reader task if running
        if self._packet_reader_task and not self._packet_reader_task.done():
            self._packet_reader_task.cancel()
            try:
                await self._packet_reader_task
            except asyncio.CancelledError:
                pass

        # Disconnect
        await self.disconnect()

    async def disconnect(self) -> bool:
        """
        Disconnect from the server and close the connection.

        Returns:
            True if disconnection successful
        """
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print("Disconnected from server")
        return True
