import socket
from . import protocol

class FreeCivClient:
    socket: socket.socket

    def connect(self, host: str, port: int) -> bool:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        return True

    def join_game(self, username: str) -> bool:
        """
        Join the game as the specified username.

        Returns:
            True if join was successful, False otherwise
        """
        try:
            # Set socket timeout to 10 seconds
            self.socket.settimeout(10.0)

            # Encode and send JOIN_REQ packet
            join_req_packet = protocol.encode_server_join_req(username)
            self.socket.sendall(join_req_packet)
            print(f"Sent JOIN_REQ for user '{username}'")

            # Read packets until we get the join reply
            # Server may send PROCESSING_STARTED before the JOIN_REPLY
            while True:
                packet_type, payload = protocol.read_packet(self.socket)
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

        except socket.timeout:
            print("Error: Socket timeout while waiting for join reply")
            return False
        except ConnectionError as e:
            print(f"Error: Connection error during join: {e}")
            return False
        except Exception as e:
            print(f"Error: Unexpected error during join: {e}")
            return False

    def disconnect(self) -> bool:
        self.socket.close()
        return True
