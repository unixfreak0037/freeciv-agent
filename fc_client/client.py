import asyncio
import traceback
from typing import Optional, Dict, Callable, Awaitable
from . import protocol
from . import handlers
from .game_state import GameState
from .packet_debugger import PacketDebugger
from .delta_cache import DeltaCache

class FreeCivClient:
    reader: Optional[asyncio.StreamReader]
    writer: Optional[asyncio.StreamWriter]
    _shutdown_event: Optional[asyncio.Event]
    _join_successful: asyncio.Event
    _packet_handlers: Dict[int, Callable[['FreeCivClient', GameState, bytes], Awaitable[None]]]
    _packet_reader_task: Optional[asyncio.Task]
    game_state: Optional[GameState]
    _packet_debugger: Optional[PacketDebugger]
    _use_two_byte_type: bool
    _delta_cache: DeltaCache

    def __init__(self, debug_packets_dir: Optional[str] = None, validate_packets: bool = False):
        self.reader = None
        self.writer = None
        self._shutdown_event = None
        self._join_successful = asyncio.Event()
        self._packet_handlers = {}
        self._packet_reader_task = None
        self.game_state = None
        self._use_two_byte_type = False  # Start with 1-byte type, switch after JOIN_REPLY
        self._delta_cache = DeltaCache()  # Cache for delta protocol
        self._validate_packets = validate_packets  # Enable validation logging

        # Initialize packet debugger if requested
        if debug_packets_dir:
            self._packet_debugger = PacketDebugger(debug_packets_dir)
            print(f"Packet debugging enabled: {debug_packets_dir}/")
        else:
            self._packet_debugger = None

        if self._validate_packets:
            print("Packet validation mode enabled")

        # Register packet handlers
        self.register_handler(protocol.PACKET_PROCESSING_STARTED, handlers.handle_processing_started)
        self.register_handler(protocol.PACKET_PROCESSING_FINISHED, handlers.handle_processing_finished)
        self.register_handler(protocol.PACKET_SERVER_JOIN_REPLY, handlers.handle_server_join_reply)
        self.register_handler(protocol.PACKET_SERVER_INFO, handlers.handle_server_info)
        self.register_handler(protocol.PACKET_GAME_INFO, handlers.handle_game_info)
        self.register_handler(protocol.PACKET_CHAT_MSG, handlers.handle_chat_msg)
        self.register_handler(protocol.PACKET_RULESET_CONTROL, handlers.handle_ruleset_control)
        self.register_handler(protocol.PACKET_RULESET_GAME, handlers.handle_ruleset_game)
        self.register_handler(protocol.PACKET_RULESET_SUMMARY, handlers.handle_ruleset_summary)
        self.register_handler(protocol.PACKET_RULESET_DESCRIPTION_PART, handlers.handle_ruleset_description_part)
        self.register_handler(protocol.PACKET_RULESET_NATION_GROUPS, handlers.handle_ruleset_nation_groups)
        self.register_handler(protocol.PACKET_RULESET_NATION, handlers.handle_ruleset_nation)
        self.register_handler(protocol.PACKET_RULESET_NATION_SETS, handlers.handle_ruleset_nation_sets)
        self.register_handler(protocol.PACKET_RULESET_DISASTER, handlers.handle_ruleset_disaster)
        self.register_handler(protocol.PACKET_RULESET_TRADE, handlers.handle_ruleset_trade)
        self.register_handler(protocol.PACKET_RULESET_ACHIEVEMENT, handlers.handle_ruleset_achievement)
        self.register_handler(protocol.PACKET_RULESET_TECH_FLAG, handlers.handle_ruleset_tech_flag)
        self.register_handler(protocol.PACKET_RULESET_UNIT_CLASS, handlers.handle_ruleset_unit_class)
        self.register_handler(protocol.PACKET_RULESET_UNIT_CLASS_FLAG, handlers.handle_ruleset_unit_class_flag)
        self.register_handler(protocol.PACKET_RULESET_TECH, handlers.handle_ruleset_tech)
        self.register_handler(protocol.PACKET_RULESET_GOVERNMENT_RULER_TITLE, handlers.handle_ruleset_government_ruler_title)
        self.register_handler(protocol.PACKET_RULESET_GOVERNMENT, handlers.handle_ruleset_government)
        self.register_handler(protocol.PACKET_RULESET_ACTION, handlers.handle_ruleset_action)
        self.register_handler(protocol.PACKET_RULESET_ACTION_ENABLER, handlers.handle_ruleset_action_enabler)
        self.register_handler(protocol.PACKET_RULESET_ACTION_AUTO, handlers.handle_ruleset_action_auto)
        self.register_handler(protocol.PACKET_NATION_AVAILABILITY, handlers.handle_nation_availability)

    def register_handler(self, packet_type: int, handler: Callable[['FreeCivClient', GameState, bytes], Awaitable[None]]) -> None:
        """
        Register a packet handler function for a specific packet type.

        Args:
            packet_type: The packet type number to handle
            handler: Async function that takes (client, game_state, payload) and processes the packet
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
        self.game_state = GameState()
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

        # Debug: Write outbound packet
        if self._packet_debugger:
            self._packet_debugger.write_outbound_packet(join_req_packet, protocol.PACKET_SERVER_JOIN_REQ)

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
                # Read next packet (now returns 3-tuple including raw bytes)
                packet_type, payload, raw_packet = await protocol.read_packet(
                    self.reader,
                    use_two_byte_type=self._use_two_byte_type,
                    validate=self._validate_packets
                )

                # Debug: Write inbound packet
                if self._packet_debugger:
                    self._packet_debugger.write_inbound_packet(raw_packet, packet_type)

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
                await handler(self, self.game_state, payload)
            else:
                # Call unknown packet handler
                await handlers.handle_unknown_packet(self, self.game_state, packet_type, payload)

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
        # Clear delta cache on disconnect
        self._delta_cache.clear_all()

        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print("Disconnected from server")
        return True
