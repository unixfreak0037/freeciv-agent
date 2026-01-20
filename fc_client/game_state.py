"""
Game state tracking for the FreeCiv client.

The GameState class maintains the current state of the game as packets
are received and processed from the server.
"""


class GameState:
    """Tracks the current game state as packets are processed."""

    def __init__(self):
        """Initialize a new game state with default values."""
        self.server_info = None
        self.chat_history = []  # List of chat message dicts with timestamps
