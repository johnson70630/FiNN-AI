#!/usr/bin/env python3
"""
Standalone script to run data collection for Finance News AI
This can be scheduled via cron or other schedulers
"""
import asyncio
import sys
import os

# Add the parent directory to the path so we can import the app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.data_collection.scraper_service import DataCollectionService

async def main():
    """Run data collection and save to data directory"""
    print("Starting data collection...")
    collector = DataCollectionService()
    new_items = await collector.update_all_data()
    print(f"Added {new_items} new items and saved to data directory")

if __name__ == "__main__":
    asyncio.run(main())