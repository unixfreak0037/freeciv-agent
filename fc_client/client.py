import asyncio
from typing import Optional
from . import protocol

class FreeCivClient:
    reader: Optional[asyncio.StreamReader]
    writer: Optional[asyncio.StreamWriter]

    def __init__(self):
        self.reader = None
        self.writer = None

    async def connect(self, host: str, port: int) -> bool:
        self.reader, self.writer = await asyncio.open_connection(host, port)
        return True

    async def join_game(self, username: str) -> bool:
        """
        Join the game as the specified username.

        Returns:
            True if join was successful, False otherwise
        """
        # Check if reader/writer are initialized
        if not self.reader or not self.writer:
            print("Error: Not connected to server")
            return False

        try:
            # Encode and send JOIN_REQ packet
            join_req_packet = protocol.encode_server_join_req(username)
            self.writer.write(join_req_packet)
            await self.writer.drain()
            print(f"Sent JOIN_REQ for user '{username}'")

            # Read packets until we get the join reply with 10 second timeout
            # Server may send PROCESSING_STARTED before the JOIN_REPLY
            async def read_join_reply():
                while True:
                    packet_type, payload = await protocol.read_packet(self.reader)
                    print(f"Received packet type: {packet_type}")

                    if packet_type == protocol.PACKET_PROCESSING_STARTED:
                        print("Received PROCESSING_STARTED (skipping)")
                        continue
                    elif packet_type == protocol.PACKET_SERVER_JOIN_REPLY:
                        # Decode payload
                        join_reply = protocol.decode_server_join_reply(payload)
                        print(f"Join reply: you_can_join={join_reply['you_can_join']}, message='{join_reply['message']}'")

                        # Check join result and return immediately
                        if join_reply['you_can_join']:
                            print(f"Successfully joined game as '{username}'")
                            return True
                        else:
                            print(f"Failed to join game: {join_reply['message']}")
                            return False
                    else:
                        # Skip other packets (e.g., packet 29) until we get the join reply
                        print(f"Skipping packet type {packet_type}")
                        continue

            return await asyncio.wait_for(read_join_reply(), timeout=10.0)

        except asyncio.TimeoutError:
            print("Error: Socket timeout while waiting for join reply")
            return False
        except ConnectionError as e:
            print(f"Error: Connection error during join: {e}")
            return False
        except Exception as e:
            print(f"Error: Unexpected error during join: {e}")
            return False

    async def disconnect(self) -> bool:
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        return True
