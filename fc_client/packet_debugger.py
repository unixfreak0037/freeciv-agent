"""
Packet debugging utility for capturing FreeCiv network packets.
"""
import os
import shutil


class PacketDebugger:
    """
    Captures FreeCiv packets to disk for protocol debugging and analysis.

    Writes packets as separate files with naming: DIRECTION_INDEX_typeNNN.packet
    - DIRECTION: "inbound" (from server) or "outbound" (to server)
    - INDEX: 4-digit zero-padded auto-incrementing counter (separate for each direction)
    - typeNNN: 3-digit zero-padded packet type number (e.g., type005, type025)

    Example: inbound_0001_type005.packet (first inbound packet, type 5)
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
            print(f"Packet debug directory '{debug_dir}' already exists. Removing it.")
            shutil.rmtree(debug_dir)

        os.makedirs(debug_dir)
        self._debug_dir = debug_dir
        self._inbound_counter = 0
        self._outbound_counter = 0

    def write_inbound_packet(self, raw_packet: bytes, packet_type: int) -> None:
        """
        Write an inbound packet (from server) to disk.

        Args:
            raw_packet: Complete raw packet bytes including header
            packet_type: The numeric packet type (e.g., 5 for SERVER_JOIN_REPLY)

        Raises:
            RuntimeError: If file write verification fails
        """
        self._inbound_counter += 1
        filename = f"inbound_{self._inbound_counter:04d}_type{packet_type:03d}.packet"
        filepath = os.path.join(self._debug_dir, filename)

        expected_size = len(raw_packet)

        with open(filepath, 'wb') as f:
            f.write(raw_packet)

        # Verify write completed successfully
        actual_size = os.path.getsize(filepath)

        if actual_size != expected_size:
            raise RuntimeError(
                f"Packet write verification failed for {filename}: "
                f"expected {expected_size} bytes, wrote {actual_size} bytes"
            )

    def write_outbound_packet(self, raw_packet: bytes, packet_type: int) -> None:
        """
        Write an outbound packet (to server) to disk.

        Args:
            raw_packet: Complete raw packet bytes including header
            packet_type: The numeric packet type (e.g., 4 for SERVER_JOIN_REQ)

        Raises:
            RuntimeError: If file write verification fails
        """
        self._outbound_counter += 1
        filename = f"outbound_{self._outbound_counter:04d}_type{packet_type:03d}.packet"
        filepath = os.path.join(self._debug_dir, filename)

        expected_size = len(raw_packet)

        with open(filepath, 'wb') as f:
            f.write(raw_packet)

        # Verify write completed successfully
        actual_size = os.path.getsize(filepath)

        if actual_size != expected_size:
            raise RuntimeError(
                f"Packet write verification failed for {filename}: "
                f"expected {expected_size} bytes, wrote {actual_size} bytes"
            )
