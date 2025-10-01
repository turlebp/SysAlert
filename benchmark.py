"""
CPU benchmark checker for monitoring provider performance.
Parses various JSON response formats and triggers alerts when thresholds are exceeded.
"""
import asyncio
import logging
import aiohttp
from typing import Optional, Tuple, Any, List, Dict
import time

logger = logging.getLogger("UltraGigaBot.benchmark")


def _parse_possible_structures(data: Any, target_name: str) -> Optional[Tuple[int, float]]:
    """
    Parse various possible JSON structures for benchmark data.
    
    Supported formats:
    1. List of dicts: [{"name": "provider", "data": [[ts, val], ...]}, ...]
    2. Dict of lists: {"provider": [[ts, val], ...], ...}
    3. CSV-like list: ["provider,ts,val", ...]
    
    Args:
        data: Parsed JSON data in various formats
        target_name: Name of the benchmark target to find
    
    Returns:
        Tuple of (timestamp, value) or None if not found
    """
    # Format 1: List of dictionaries
    if isinstance(data, list) and len(data) > 0:
        # Check if it's CSV-like strings
        if isinstance(data[0], str):
            result = None
            for line in data:
                parts = line.split(',')
                if len(parts) >= 3 and parts[0].strip() == target_name:
                    try:
                        ts = int(parts[1].strip())
                        val = float(parts[2].strip())
                        result = (ts, val)  # Keep updating to get last match
                    except (ValueError, IndexError):
                        continue
            return result
        
        # Check if it's list of dicts
        if isinstance(data[0], dict):
            for item in data:
                if item.get("name") == target_name:
                    series_data = item.get("data", [])
                    if series_data and len(series_data) > 0:
                        last_point = series_data[-1]
                        if len(last_point) >= 2:
                            return (int(last_point[0]), float(last_point[1]))
            return None
    
    # Format 2: Dictionary of name -> data points
    if isinstance(data, dict):
        if target_name in data:
            series_data = data[target_name]
            if isinstance(series_data, list) and len(series_data) > 0:
                last_point = series_data[-1]
                if isinstance(last_point, (list, tuple)) and len(last_point) >= 2:
                    return (int(last_point[0]), float(last_point[1]))
    
    return None


async def check_cpu_benchmark(
    url: str,
    target_name: str,
    threshold: float,
    timeout: float = 10.0
) -> Tuple[bool, Optional[float], str]:
    """
    Fetch CPU benchmark data and check against threshold.
    
    Args:
        url: Benchmark API endpoint
        target_name: Provider name to check (e.g., "turtlebp")
        threshold: Alert threshold in seconds
        timeout: HTTP request timeout
    
    Returns:
        Tuple of (alert_triggered, value, message)
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    return False, None, f"HTTP {resp.status}"
                
                data = await resp.json()
                
                # Try to parse the response
                result = _parse_possible_structures(data, target_name)
                
                if result is None:
                    return False, None, f"Target '{target_name}' not found in response"
                
                timestamp, value = result
                
                # Check threshold
                if value > threshold:
                    msg = f"⚠️ CPU Benchmark Alert: {target_name} = {value:.3f}s (threshold: {threshold}s)"
                    logger.warning(msg)
                    return True, value, msg
                else:
                    logger.info(f"CPU benchmark OK: {target_name} = {value:.3f}s")
                    return False, value, "OK"
                
    except asyncio.TimeoutError:
        return False, None, "Request timeout"
    except aiohttp.ClientError as e:
        return False, None, f"HTTP error: {e}"
    except Exception as e:
        logger.exception("Unexpected error in CPU benchmark check")
        return False, None, f"Error: {e}"


async def benchmark_monitor_loop(
    db,
    tele_queue,
    config: Dict[str, Any],
    admin_chat_ids: List[int]
) -> None:
    """
    Background task that periodically checks CPU benchmarks.
    Only sends alerts to admin users.
    
    Args:
        db: Database instance
        tele_queue: TeleQueue for sending alerts
        config: Configuration dict
        admin_chat_ids: List of admin chat IDs to notify
    """
    bench_config = config.get("cpu_benchmark", {})
    
    if not bench_config.get("enabled", True):
        logger.info("CPU benchmark monitoring disabled")
        return
    
    url = bench_config.get("url")
    threshold = float(bench_config.get("threshold_seconds", 0.35))
    interval = int(bench_config.get("poll_interval_seconds", 300))
    target_name = "turtlebp"  # Hardcoded for now, could be configurable
    
    if not url:
        logger.warning("CPU benchmark URL not configured, monitoring disabled")
        return
    
    logger.info(f"Starting CPU benchmark monitor (interval: {interval}s, threshold: {threshold}s)")
    
    while True:
        try:
            alert_triggered, value, message = await check_cpu_benchmark(
                url, target_name, threshold
            )
            
            # Record in history/audit
            if alert_triggered and admin_chat_ids:
                # Send to all admins
                for admin_id in admin_chat_ids:
                    try:
                        await tele_queue.enqueue(admin_id, message)
                    except Exception:
                        logger.exception(f"Failed to enqueue benchmark alert to admin {admin_id}")
                
                # Record in database
                try:
                    await asyncio.to_thread(
                        db.audit,
                        0,  # System action
                        "cpu_benchmark_alert",
                        f"{target_name}: {value:.3f}s > {threshold}s"
                    )
                except Exception:
                    logger.exception("Failed to record benchmark alert in audit log")
            
        except Exception:
            logger.exception("Error in benchmark monitor loop")
        
        await asyncio.sleep(interval)