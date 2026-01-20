"""
Packet debugging utility for capturing FreeCiv network packets.
"""
import os


class PacketDebugger:
    """
    Captures FreeCiv packets to disk for protocol debugging and analysis.

    Writes packets as separate files with naming: DIRECTION_NUMBER.packet
    - DIRECTION: "inbound" (from server) or "outbound" (to server)
    - NUMBER: auto-incrementing counter (separate for each direction)
    """

    def __init__(self, debug_dir: str):
        """
        Initialize packet debugger and create output directory.

        Args:
            debug_dir: Directory path to store packet files

        Raises:
            FileExistsError: If debug_dir already exists (prevents accidental overwrites)
        """
        if os.path.exists(debug_dir):
            raise FileExistsError(
                f"Packet debug directory '{debug_dir}' already exists. "
                "Remove it or choose a different directory."
            )

        os.makedirs(debug_dir)
        self._debug_dir = debug_dir
        self._inbound_counter = 0
        self._outbound_counter = 0

    def write_inbound_packet(self, raw_packet: bytes) -> None:
        """
        Write an inbound packet (from server) to disk.

        Args:
            raw_packet: Complete raw packet bytes including header
        """
        self._inbound_counter += 1
        filename = f"inbound_{self._inbound_counter}.packet"
        filepath = os.path.join(self._debug_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(raw_packet)

    def write_outbound_packet(self, raw_packet: bytes) -> None:
        """
        Write an outbound packet (to server) to disk.

        Args:
            raw_packet: Complete raw packet bytes including header
        """
        self._outbound_counter += 1
        filename = f"outbound_{self._outbound_counter}.packet"
        filepath = os.path.join(self._debug_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(raw_packet)
