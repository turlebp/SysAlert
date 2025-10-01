#!/usr/bin/env python3
"""
Migrate targets from YAML config to database.
Non-destructive: only adds new targets, doesn't remove existing ones.
"""
import os
import sys
import yaml
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from db import DB

load_dotenv()


def main():
    """Migrate YAML config to database."""
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    
    if not os.path.exists(config_file):
        print(f"ERROR: Config file not found: {config_file}")
        sys.exit(1)
    
    print(f"Loading config from: {config_file}")
    
    with open(config_file, "r") as f:
        config = yaml.safe_load(f) or {}
    
    targets = config.get("targets", [])
    
    if not targets:
        print("No targets found in YAML config")
        print("Expected format:")
        print("  targets:")
        print("    - name: server1")
        print("      ip: 192.168.1.1")
        print("      port: 9876")
        sys.exit(0)
    
    print(f"\nFound {len(targets)} targets in config file")
    print("\nTargets will be added to a default admin customer (chat_id=0)")
    print("This is a special admin account for managing targets.")
    print("\nWARNING: This operation modifies the database.")
    
    confirm = input("\nProceed with migration? (yes/no): ")
    
    if confirm.strip().lower() != "yes":
        print("Migration aborted")
        sys.exit(0)
    
    # Initialize database
    db = DB()
    
    # Ensure admin customer exists (chat_id=0)
    admin_customer = db.get_customer_by_chat(0)
    if not admin_customer:
        print("\nCreating admin customer (chat_id=0)...")
        db.create_customer(0, interval_seconds=60, failure_threshold=1)
        admin_customer = db.get_customer_by_chat(0)
    
    # Migrate targets
    print(f"\nMigrating {len(targets)} targets...")
    
    for target in targets:
        name = target.get("name")
        ip = target.get("ip")
        port = target.get("port")
        
        if not all([name, ip, port]):
            print(f"⚠️  Skipping invalid target: {target}")
            continue
        
        try:
            port = int(port)
            db.upsert_target(admin_customer.id, name, ip, port)
            print(f"✅ Migrated: {name} ({ip}:{port})")
        except Exception as e:
            print(f"❌ Failed to migrate {name}: {e}")
    
    print("\n✅ Migration complete!")
    print("\nNext steps:")
    print("1. Add subscriptions for users: scripts/add_subscriber.py <key> <chat_id>")
    print("2. Or use SQL: sqlite3 data/bot.db \"INSERT INTO subscriptions VALUES (<chat_id>, strftime('%s', 'now'));\"")
    print("3. Targets can be managed per customer via SQL or API")


if __name__ == "__main__":
    main()