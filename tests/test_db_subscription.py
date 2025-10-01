"""
Test database operations for subscriptions and customers.
"""
import pytest
from db import DB


def test_add_remove_subscription(temp_db):
    """Test adding and removing subscriptions."""
    db = temp_db
    
    # Add subscription
    db.add_subscription(12345)
    subs = db.list_subscriptions()
    assert 12345 in subs
    
    # Check is_subscribed
    assert db.is_subscribed(12345) is True
    assert db.is_subscribed(99999) is False
    
    # Remove subscription
    db.remove_subscription(12345)
    subs2 = db.list_subscriptions()
    assert 12345 not in subs2


def test_subscription_idempotent(temp_db):
    """Test that adding same subscription twice is safe."""
    db = temp_db
    
    db.add_subscription(12345)
    db.add_subscription(12345)  # Should not error
    
    subs = db.list_subscriptions()
    assert subs.count(12345) == 1


def test_customer_crud(temp_db):
    """Test customer CRUD operations."""
    db = temp_db
    
    # Create customer
    customer = db.create_customer(12345, interval_seconds=120, failure_threshold=5)
    assert customer.chat_id == 12345
    assert customer.interval_seconds == 120
    
    # Get customer
    retrieved = db.get_customer_by_chat(12345)
    assert retrieved is not None
    assert retrieved.chat_id == 12345
    assert retrieved.interval_seconds == 120
    
    # Update customer
    db.update_customer(12345, interval_seconds=180)
    updated = db.get_customer_by_chat(12345)
    assert updated.interval_seconds == 180


def test_target_operations(temp_db):
    """Test target CRUD operations."""
    db = temp_db
    
    # Create customer first
    customer = db.create_customer(12345)
    
    # Add target
    target = db.upsert_target(customer.id, "test_server", "192.168.1.1", 9876)
    assert target.name == "test_server"
    assert target.ip == "192.168.1.1"
    assert target.port == 9876
    
    # List targets
    targets = db.list_customer_targets(customer.id)
    assert len(targets) == 1
    assert targets[0].name == "test_server"
    
    # Update target (upsert with same name)
    updated = db.upsert_target(customer.id, "test_server", "192.168.1.2", 8888)
    assert updated.ip == "192.168.1.2"
    assert updated.port == 8888
    
    # Should still have only one target
    targets = db.list_customer_targets(customer.id)
    assert len(targets) == 1
    
    # Remove target
    removed = db.remove_target(customer.id, "test_server")
    assert removed is True
    
    targets = db.list_customer_targets(customer.id)
    assert len(targets) == 0


def test_history_recording(temp_db):
    """Test history recording."""
    db = temp_db
    
    # Write history entries
    db.write_history(12345, "server1", "success", "", 0.123)
    db.write_history(12345, "server1", "failure", "Connection refused", 0.0)
    
    # Get recent history
    history = db.get_recent_history(12345, limit=10)
    assert len(history) == 2
    assert history[0].status in ["success", "failure"]


def test_audit_logging(temp_db):
    """Test audit logging."""
    db = temp_db
    
    db.audit(12345, "add_target", "Added target: server1")
    db.audit(12345, "remove_target", "Removed target: server2")
    
    # Audit logs are written, no errors should occur
    # In production, you'd query these for admin review