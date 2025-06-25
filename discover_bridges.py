#!/usr/bin/env python3
"""Bridge Discovery Script"""

import asyncio
import json
from empire_bridge_discovery import EmpireBridgeDiscovery

async def main():
    """Run bridge discovery and print results as JSON"""
    bridges = await EmpireBridgeDiscovery.discover_all_bridges()
    print(json.dumps(bridges))

if __name__ == "__main__":
    asyncio.run(main())
