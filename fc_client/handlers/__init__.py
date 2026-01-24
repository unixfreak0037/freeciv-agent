"""
Packet handler functions for the FreeCiv client.

Each handler is an async function that processes a specific packet type.
Handlers receive the client instance and the packet payload, and are
responsible for decoding the payload and updating client state as needed.
"""

from typing import TYPE_CHECKING
from .. import protocol
from ..game_state import GameState, RulesetControl

if TYPE_CHECKING:
    from ..client import FreeCivClient

from .general import *
from .pregame import *
from .info import *
from .chat import *
from .ruleset import *
from .ruleset import *
from .unknown import *