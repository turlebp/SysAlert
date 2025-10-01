#!/usr/bin/env python3
"""
Admin script to add a subscriber.
Requires ADMIN_API_KEY environment variable for security.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from db import DB

load_dotenv()


def main():
    """Add a subscriber via command line."""
    admin_key = os.getenv("ADMIN_API_KEY")
    
    if not admin_key:
        print("ERROR: ADMIN_API_KEY environment variable not set")
        print("Set it in .env file or export it before running this script")
        sys.exit(1)
    
    if len(sys.argv) != 3:
        print("Usage: add_subscriber.py <API_KEY> <chat_id>")
        print("\nExample:")
        print("  python scripts/add_subscriber.py your_api_key 123456789")
        sys.exit(2)
    
    provided_key = sys.argv[1]
    
    if provided_key != admin_key:
        print("ERROR: Invalid API key")
        sys.exit(3)
    
    try:
        chat_id = int(sys.argv[2])
    except ValueError:
        print("ERROR: chat_id must be an integer")
        sys.exit(4)
    
    # Initialize DB and add subscription
    db = DB()
    db.add_subscription(chat_id)
    
    print(f"✅ Successfully added subscription for chat_id: {chat_id}")
    
    # Check if customer config exists
    customer = db.get_customer_by_chat(chat_id)
    if not customer:
        print(f"⚠️  No customer config found. Creating default config...")
        db.create_customer(chat_id)
        print(f"✅ Created default customer config")
    
    print("\nSubscription active. User can now use the bot.")


if __name__ == "__main__":
    main()