"""
Test TeleQueue functionality.
"""
import pytest
import asyncio
from services.tele_queue import TeleQueue


@pytest.mark.asyncio
async def test_tele_queue_basic():
    """Test basic queue operations."""
    sent_messages = []
    
    async def mock_send(chat_id, text):
        sent_messages.append((chat_id, text))
    
    queue = TeleQueue(mock_send, workers=2, per_chat_rate_seconds=0.1)
    await queue.start()
    
    try:
        # Enqueue messages
        await queue.enqueue(123, "Test message 1")
        await queue.enqueue(456, "Test message 2")
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Check messages were sent
        assert len(sent_messages) == 2
        assert (123, "Test message 1") in sent_messages
        assert (456, "Test message 2") in sent_messages
        
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_tele_queue_rate_limiting():
    """Test per-chat rate limiting."""
    sent_times = []
    
    async def mock_send(chat_id, text):
        sent_times.append((chat_id, asyncio.get_event_loop().time()))
    
    queue = TeleQueue(mock_send, workers=1, per_chat_rate_seconds=0.2)
    await queue.start()
    
    try:
        # Send multiple messages to same chat
        await queue.enqueue(123, "Message 1")
        await queue.enqueue(123, "Message 2")
        await queue.enqueue(123, "Message 3")
        
        # Wait for processing
        await asyncio.sleep(1.0)
        
        # Check that messages were rate-limited
        assert len(sent_times) == 3
        
        # Check time between messages
        for i in range(1, len(sent_times)):
            time_diff = sent_times[i][1] - sent_times[i-1][1]
            assert time_diff >= 0.15  # Allow small variance
        
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_tele_queue_retry_on_failure():
    """Test retry logic on failures."""
    attempt_count = [0]
    
    async def mock_send_fail_once(chat_id, text):
        attempt_count[0] += 1
        if attempt_count[0] == 1:
            raise Exception("Temporary failure")
        # Success on retry
    
    queue = TeleQueue(mock_send_fail_once, workers=1)
    await queue.start()
    
    try:
        await queue.enqueue(123, "Test message")
        await asyncio.sleep(2.0)  # Wait for retry
        
        # Should have retried and succeeded
        assert attempt_count[0] >= 2
        
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_tele_queue_stats():
    """Test queue statistics."""
    async def mock_send(chat_id, text):
        pass
    
    queue = TeleQueue(mock_send, workers=1)
    await queue.start()
    
    try:
        await queue.enqueue(123, "Test")
        await asyncio.sleep(0.5)
        
        stats = queue.get_stats()
        assert "sent" in stats
        assert "failed" in stats
        assert "dropped" in stats
        assert stats["sent"] >= 1
        
    finally:
        await queue.stop()