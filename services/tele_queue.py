"""
TeleQueue: Reliable message delivery queue with rate limiting and exponential backoff.
Handles Telegram API rate limits and transient failures gracefully.
"""
import asyncio
import random
import logging
from typing import Callable, Awaitable, Any, Dict
from collections import defaultdict

logger = logging.getLogger("UltraGigaBot.tele_queue")


class TeleQueue:
    """
    Asynchronous message queue with:
    - Per-chat rate limiting
    - Exponential backoff on failures
    - Retry with jitter
    - Graceful shutdown
    - Respect for Telegram retry_after headers
    """
    
    def __init__(
        self,
        bot_send: Callable[..., Awaitable[Any]],
        workers: int = 3,
        per_chat_rate_seconds: float = 1.0,
        max_attempts: int = 5
    ):
        """
        Initialize TeleQueue.
        
        Args:
            bot_send: Async function to send messages (takes chat_id, text)
            workers: Number of concurrent worker tasks
            per_chat_rate_seconds: Minimum seconds between messages to same chat
            max_attempts: Maximum retry attempts before dropping message
        """
        self._q = asyncio.Queue()
        self._workers = workers
        self._bot_send = bot_send
        self._tasks = []
        self._running = False
        self._per_chat_rate_seconds = per_chat_rate_seconds
        self._max_attempts = max_attempts
        self._last_sent: Dict[int, float] = {}  # chat_id -> timestamp
        self._stats = {"sent": 0, "failed": 0, "dropped": 0}
    
    async def start(self) -> None:
        """Start worker tasks."""
        if self._running:
            logger.warning("TeleQueue already running")
            return
        
        self._running = True
        for i in range(self._workers):
            task = asyncio.create_task(self._worker(i))
            self._tasks.append(task)
        
        logger.info(f"TeleQueue started with {self._workers} workers")
    
    async def stop(self) -> None:
        """Stop workers gracefully."""
        self._running = False
        
        # Cancel all workers
        for task in self._tasks:
            task.cancel()
        
        # Wait for cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("TeleQueue stopped gracefully")
    
    async def enqueue(self, chat_id: int, text: str) -> None:
        """Add a message to the queue."""
        await self._q.put({
            "chat_id": chat_id,
            "text": text,
            "attempts": 0
        })
        logger.debug(f"Enqueued message to {chat_id}: {text[:50]}...")
    
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._q.qsize()
    
    def get_stats(self) -> Dict[str, int]:
        """Get delivery statistics."""
        return self._stats.copy()
    
    async def _worker(self, worker_id: int) -> None:
        """Worker task that processes queue items."""
        logger.debug(f"Worker {worker_id} started")
        
        while self._running:
            try:
                # Get item with timeout to allow checking _running flag
                item = await asyncio.wait_for(self._q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            
            try:
                await self._send_with_backoff(item, worker_id)
            except Exception:
                logger.exception(f"Worker {worker_id}: Unhandled error processing item")
            finally:
                try:
                    self._q.task_done()
                except Exception:
                    pass
        
        logger.debug(f"Worker {worker_id} stopped")
    
    async def _send_with_backoff(self, item: Dict, worker_id: int) -> None:
        """
        Attempt to send message with exponential backoff and rate limiting.
        """
        chat_id = item["chat_id"]
        text = item["text"]
        
        while item["attempts"] < self._max_attempts:
            # Apply per-chat rate limiting
            now = asyncio.get_event_loop().time()
            last_sent = self._last_sent.get(chat_id, 0)
            wait_time = max(0, self._per_chat_rate_seconds - (now - last_sent))
            
            if wait_time > 0:
                logger.debug(f"Worker {worker_id}: Rate limiting chat {chat_id}, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            try:
                # Attempt send
                logger.debug(f"Worker {worker_id}: Sending to {chat_id} (attempt {item['attempts'] + 1})")
                await self._bot_send(chat_id=chat_id, text=text)
                
                # Success
                self._last_sent[chat_id] = asyncio.get_event_loop().time()
                self._stats["sent"] += 1
                logger.info(f"Worker {worker_id}: Successfully sent to {chat_id}")
                return
                
            except Exception as e:
                item["attempts"] += 1
                self._stats["failed"] += 1
                
                # Check for Telegram-specific retry_after header
                retry_after = getattr(e, "retry_after", None)
                
                # Calculate backoff with exponential increase and jitter
                base_delay = 1.0
                exponential = base_delay * (2 ** (item["attempts"] - 1))
                jitter = random.uniform(0, 0.5)
                delay = min(60, exponential + jitter)
                
                # Use Telegram's suggested delay if provided
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except (TypeError, ValueError):
                        pass
                
                logger.warning(
                    f"Worker {worker_id}: Failed to send to {chat_id} "
                    f"(attempt {item['attempts']}/{self._max_attempts}). "
                    f"Retrying in {delay:.1f}s. Error: {e}"
                )
                
                if item["attempts"] < self._max_attempts:
                    await asyncio.sleep(delay)
        
        # Max attempts exceeded - drop message
        self._stats["dropped"] += 1
        logger.error(
            f"Worker {worker_id}: Dropping message to {chat_id} after "
            f"{self._max_attempts} attempts"
        )