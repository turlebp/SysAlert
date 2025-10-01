"""
TCP monitoring service with asyncio-based connection checks.
Includes scheduler orchestration for checking multiple targets concurrently.
"""
import asyncio
import time
import logging
from typing import Tuple, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger("UltraGigaBot.monitor")


async def tcp_check(ip: str, port: int, timeout: float = 5.0) -> Tuple[bool, float, str]:
    """
    Attempt to establish TCP connection to target.
    
    Args:
        ip: Target IP address
        port: Target port number
        timeout: Connection timeout in seconds
    
    Returns:
        Tuple of (success, response_time_seconds, error_message)
    """
    start = time.time()
    
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host=ip, port=port),
            timeout=timeout
        )
        
        # Clean close
        writer.close()
        await writer.wait_closed()
        
        response_time = time.time() - start
        logger.debug(f"TCP check succeeded: {ip}:{port} ({response_time:.3f}s)")
        return True, response_time, ""
        
    except asyncio.TimeoutError:
        error_msg = f"Connection timeout after {timeout}s"
        logger.debug(f"TCP check failed: {ip}:{port} - {error_msg}")
        return False, 0.0, error_msg
        
    except ConnectionRefusedError:
        error_msg = "Connection refused"
        logger.debug(f"TCP check failed: {ip}:{port} - {error_msg}")
        return False, 0.0, error_msg
        
    except OSError as e:
        error_msg = f"OS error: {e}"
        logger.debug(f"TCP check failed: {ip}:{port} - {error_msg}")
        return False, 0.0, error_msg
        
    except Exception as e:
        error_msg = str(e)
        logger.exception(f"TCP check unexpected error: {ip}:{port}")
        return False, 0.0, error_msg


async def run_checks_for_customer(
    db,
    tele_queue,
    customer,
    semaphore: asyncio.Semaphore,
    config: Dict[str, Any]
) -> None:
    """
    Run TCP checks for all enabled targets belonging to a customer.
    
    Args:
        db: Database instance
        tele_queue: TeleQueue instance for sending alerts
        customer: Customer ORM object with loaded targets
        semaphore: Semaphore to limit concurrent checks
        config: Configuration dictionary
    """
    if not customer.alerts_enabled:
        logger.debug(f"Skipping checks for customer {customer.chat_id} (alerts disabled)")
        return
    
    # Enforce minimum interval
    min_interval = config.get("min_interval_seconds", 20)
    interval = max(int(customer.interval_seconds or 60), min_interval)
    
    check_tasks = []
    now_ts = int(datetime.now(timezone.utc).timestamp())
    
    for target in customer.targets:
        if not target.enabled:
            continue
        
        # Check if due for checking based on last_checked and interval
        last_checked = int(target.last_checked or 0)
        time_since_check = now_ts - last_checked
        
        if time_since_check < interval:
            logger.debug(
                f"Target {target.name} not due yet "
                f"(checked {time_since_check}s ago, interval {interval}s)"
            )
            continue
        
        # Create check task
        task = asyncio.create_task(
            _check_target(
                db, tele_queue, customer, target,
                semaphore, config, now_ts
            )
        )
        check_tasks.append(task)
    
    if check_tasks:
        logger.info(f"Running {len(check_tasks)} checks for customer {customer.chat_id}")
        await asyncio.gather(*check_tasks, return_exceptions=True)


async def _check_target(
    db,
    tele_queue,
    customer,
    target,
    semaphore: asyncio.Semaphore,
    config: Dict[str, Any],
    check_timestamp: int
) -> None:
    """Internal helper to check a single target with semaphore."""
    
    async with semaphore:
        timeout = config.get("connection_timeout", 10)
        
        # Perform TCP check
        success, response_time, error_msg = await tcp_check(
            target.ip,
            target.port,
            timeout=timeout
        )
        
        # Record result in history (thread-safe DB call)
        try:
            await asyncio.to_thread(
                db.write_history,
                customer.chat_id,
                target.name,
                "success" if success else "failure",
                error_msg,
                response_time
            )
        except Exception:
            logger.exception(f"Failed to write history for target {target.name}")
        
        # Update target's last_checked and failure count
        try:
            await asyncio.to_thread(
                db.update_target_checked,
                target.id,
                check_timestamp,
                not success
            )
        except Exception:
            logger.exception(f"Failed to update last_checked for target {target.name}")
        
        # Handle failure alerts
        if not success:
            # Reload target to get updated consecutive_failures
            try:
                updated_target = await asyncio.to_thread(
                    db.session().get,
                    type(target),
                    target.id
                )
                consecutive_failures = updated_target.consecutive_failures if updated_target else 1
            except Exception:
                consecutive_failures = 1
            
            # Check if we should send alert based on threshold
            failure_threshold = customer.failure_threshold or 3
            
            if consecutive_failures >= failure_threshold:
                alert_msg = (
                    f"🔴 ALERT: {target.name} is DOWN\n"
                    f"Target: {target.ip}:{target.port}\n"
                    f"Consecutive failures: {consecutive_failures}\n"
                    f"Error: {error_msg}\n"
                    f"Response time: {response_time:.3f}s"
                )
                
                try:
                    await tele_queue.enqueue(customer.chat_id, alert_msg)
                    logger.info(f"Alert enqueued for {customer.chat_id}: {target.name} is DOWN")
                except Exception:
                    logger.exception(f"Failed to enqueue alert for target {target.name}")
        
        else:
            # Success - if target was previously failing, send recovery notice
            if target.consecutive_failures > 0:
                recovery_msg = (
                    f"✅ RECOVERED: {target.name} is UP\n"
                    f"Target: {target.ip}:{target.port}\n"
                    f"Response time: {response_time:.3f}s"
                )
                
                try:
                    await tele_queue.enqueue(customer.chat_id, recovery_msg)
                    logger.info(f"Recovery alert enqueued for {customer.chat_id}: {target.name}")
                except Exception:
                    logger.exception(f"Failed to enqueue recovery alert for target {target.name}")