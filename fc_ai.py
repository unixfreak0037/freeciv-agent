#!/usr/bin/env python3

import asyncio
import os
import sys

from fc_client.client import FreeCivClient

async def main() -> int:
    client = FreeCivClient()
    await client.connect("192.168.86.33", 6556)
    await client.join_game("ai-user")
    await client.disconnect()
    return os.EX_OK

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))