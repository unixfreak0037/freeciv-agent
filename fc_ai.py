#!/usr/bin/env python3

import os
import sys

from fc_client.client import FreeCivClient

def main() -> int:
    client = FreeCivClient()
    client.connect("192.168.86.33", 6556)
    client.join_game("ai-user")
    client.disconnect()
    return os.EX_OK

if __name__ == "__main__":
    sys.exit(main())