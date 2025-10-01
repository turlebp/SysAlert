
import os
import sys
import asyncio
import logging
import signal
from typing import Dict, Any, List
import yaml
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
import ipaddress

from db import DB
from services.tele_queue import TeleQueue
from services.monitor import run_checks_for_customer
from benchmark import benchmark_monitor_loop

# Load environment variables
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger("UltraGigaBot")

# Global state
db: DB = None
tele_queue: TeleQueue = None
application: Application = None
config: Dict[str, Any] = {}
background_tasks: List[asyncio.Task] = []


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML and environment variables.
    Environment variables take precedence over config file.
    """
    # Load YAML config (non-sensitive defaults)
    conf = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            conf = yaml.safe_load(f) or {}
        logger.info(f"Loaded config from {path}")
    elif os.path.exists("config.yaml.example"):
        with open("config.yaml.example", "r") as f:
            conf = yaml.safe_load(f) or {}
        logger.warning("Using config.yaml.example as config file not found")
    
    # Override with environment variables (sensitive data)
    conf["telegram_token"] = os.getenv("TELEGRAM_TOKEN", conf.get("telegram_token"))
    
    # Parse admin user IDs
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    if admin_ids_str:
        conf["admin_user_ids"] = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]
    else:
        conf["admin_user_ids"] = conf.get("admin_user_ids", [])
    
    conf["admin_api_key"] = os.getenv("ADMIN_API_KEY", conf.get("admin_api_key"))
    conf["db_url"] = os.getenv("DB_URL", conf.get("db_url", "sqlite:///./data/bot.db"))
    conf["min_interval_seconds"] = int(os.getenv("MIN_INTERVAL_SECONDS", conf.get("min_interval_seconds", 20)))
    conf["max_concurrent_checks"] = int(os.getenv("MAX_CONCURRENT_CHECKS", conf.get("max_concurrent_checks", 50)))
    conf["tele_workers"] = int(os.getenv("TELE_WORKERS", conf.get("tele_workers", 3)))
    
    # CPU benchmark config
    if "cpu_benchmark" not in conf:
        conf["cpu_benchmark"] = {}
    
    bench = conf["cpu_benchmark"]
    bench["enabled"] = os.getenv("CPU_BENCH_ENABLED", str(bench.get("enabled", "true"))).lower() == "true"
    bench["url"] = os.getenv("CPU_BENCH_URL", bench.get("url", ""))
    bench["threshold_seconds"] = float(os.getenv("CPU_BENCH_THRESHOLD_SECONDS", bench.get("threshold_seconds", 0.35)))
    bench["poll_interval_seconds"] = int(os.getenv("CPU_BENCH_INTERVAL", bench.get("poll_interval_seconds", 300)))
    
    return conf


def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in config.get("admin_user_ids", [])



# === Bot Command Handlers ===
async def add_target_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User command: /addtarget <name> <ip> <port>"""
    chat_id = update.effective_chat.id
    if not await asyncio.to_thread(db.is_subscribed, chat_id):
        await update.message.reply_text("You are not subscribed.")
        return
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /addtarget <name> <ip> <port>\nExample: /addtarget MyServer 192.168.1.100 9876")
        return
    name, ip, port_str = context.args
    # Validate IP
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        await update.message.reply_text(f"Invalid IP address: {ip}")
        return
    # Validate port
    try:
        port = int(port_str)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"Invalid port: {port_str} (must be 1-65535)")
        return
    # Validate name
    if len(name) > 50 or not name.replace('_', '').replace('-', '').isalnum():
        await update.message.reply_text("Invalid name (max 50 chars, alphanumeric + _ - only)")
        return
    # Get or create customer
    customer = await asyncio.to_thread(db.get_customer_by_chat, chat_id)
    if not customer:
        customer = await asyncio.to_thread(db.create_customer, chat_id)
    # Add target
    await asyncio.to_thread(db.upsert_target, customer.id, name, ip, port)
    await asyncio.to_thread(db.audit, chat_id, "add_target", f"{name} {ip}:{port}")
    await update.message.reply_text(f"✅ Added target: {name} ({ip}:{port})")

async def remove_target_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User command: /removetarget <name>"""
    chat_id = update.effective_chat.id
    if not await asyncio.to_thread(db.is_subscribed, chat_id):
        await update.message.reply_text("You are not subscribed.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /removetarget <name>")
        return
    name = context.args[0]
    customer = await asyncio.to_thread(db.get_customer_by_chat, chat_id)
    if not customer:
        await update.message.reply_text("No configuration found.")
        return
    removed = await asyncio.to_thread(db.remove_target, customer.id, name)
    if removed:
        await asyncio.to_thread(db.audit, chat_id, "remove_target", name)
        await update.message.reply_text(f"✅ Removed target: {name}")
    else:
        await update.message.reply_text(f"Target not found: {name}")

async def set_interval_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User command: /setinterval <seconds>"""
    chat_id = update.effective_chat.id
    if not await asyncio.to_thread(db.is_subscribed, chat_id):
        await update.message.reply_text("You are not subscribed.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /setinterval <seconds>")
        return
    try:
        interval = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Interval must be a number")
        return
    min_interval = config.get("min_interval_seconds", 20)
    if interval < min_interval:
        await update.message.reply_text(f"Interval too low. Minimum: {min_interval}s")
        return
    await asyncio.to_thread(db.update_customer, chat_id, interval_seconds=interval)
    await asyncio.to_thread(db.audit, chat_id, "set_interval", str(interval))
    await update.message.reply_text(f"✅ Check interval set to {interval}s")

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's chat_id and subscription status."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    is_subbed = await asyncio.to_thread(db.is_subscribed, chat_id)
    is_adm = is_admin(user_id)
    
    msg = f"📋 Your Information:\n"
    msg += f"Chat ID: {chat_id}\n"
    msg += f"User ID: {user_id}\n"
    msg += f"Subscribed: {'✅ Yes' if is_subbed else '❌ No'}\n"
    msg += f"Admin: {'✅ Yes' if is_adm else '❌ No'}\n\n"
    
    if not is_subbed:
        msg += "To subscribe, ask an admin to add your chat_id."
    
    await update.message.reply_text(msg)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Start command handler.
    Does NOT auto-subscribe users - admin approval required.
    """
    msg = (
        "👋 Welcome to UltraGiga Monitor Bot!\n\n"
        "This bot monitors your servers and alerts you when issues are detected.\n\n"
        "ℹ️ Note: This bot requires admin approval to use.\n"
        "Use /whoami to get your chat_id and ask an admin to add you.\n\n"
        "Available commands:\n"
        "/whoami - Show your chat ID\n"
        "/status - View your monitored targets\n"
        "/help - Show help message"
    )
    await update.message.reply_text(msg)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show status of monitored targets for this chat."""
    chat_id = update.effective_chat.id
    
    # Check subscription
    is_subbed = await asyncio.to_thread(db.is_subscribed, chat_id)
    if not is_subbed:
        await update.message.reply_text("❌ You are not subscribed. Use /whoami to get your chat_id.")
        return
    
    # Get customer config
    customer = await asyncio.to_thread(db.get_customer_by_chat, chat_id)
    if not customer:
        await update.message.reply_text(
            "No monitoring configuration found.\n"
            "Ask an admin to configure targets for your account."
        )
        return
    
    # Build status message
    msg = f"📊 Monitoring Status\n\n"
    msg += f"Alerts: {'✅ Enabled' if customer.alerts_enabled else '❌ Disabled'}\n"
    msg += f"Check Interval: {customer.interval_seconds}s\n"
    msg += f"Failure Threshold: {customer.failure_threshold}\n\n"
    
    targets = customer.targets
    if not targets:
        msg += "No targets configured."
    else:
        msg += f"Targets ({len(targets)}):\n"
        for t in targets:
            status = "✅" if t.enabled else "❌"
            failures = f" ({t.consecutive_failures} failures)" if t.consecutive_failures > 0 else ""
            msg += f"{status} {t.name}: {t.ip}:{t.port}{failures}\n"
    
    await update.message.reply_text(msg)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message with available commands."""
    user_id = update.effective_user.id
    is_adm = is_admin(user_id)
    chat_id = update.effective_chat.id
    is_subbed = await asyncio.to_thread(db.is_subscribed, chat_id)
    msg = "📚 Available Commands:\n\n"
    msg += "🔹 Basic:\n"
    msg += "/start - Welcome message\n"
    msg += "/whoami - Show your chat ID\n"
    msg += "/help - Show this help\n\n"
    if is_subbed:
        msg += "🔹 Monitoring:\n"
        msg += "/status - View your targets\n"
        msg += "/history - Recent check history\n"
        msg += "/addtarget <name> <ip> <port> - Add target\n"
        msg += "/removetarget <name> - Remove target\n"
        msg += "/setinterval <seconds> - Set check interval\n\n"
    if is_adm:
        msg += "🔹 Admin:\n"
        msg += "/addsub <chat_id> - Add subscription\n"
        msg += "/rmsub <chat_id> - Remove subscription\n"
        msg += "/stats - Bot statistics\n"
    await update.message.reply_text(msg)


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent check history."""
    chat_id = update.effective_chat.id
    
    is_subbed = await asyncio.to_thread(db.is_subscribed, chat_id)
    if not is_subbed:
        await update.message.reply_text("❌ You are not subscribed.")
        return
    
    history = await asyncio.to_thread(db.get_recent_history, chat_id, limit=10)
    
    if not history:
        await update.message.reply_text("No history available.")
        return
    
    msg = "📜 Recent History (last 10 checks):\n\n"
    for h in history:
        status_icon = "✅" if h.status == "success" else "❌"
        from datetime import datetime
        dt = datetime.fromtimestamp(h.timestamp)
        msg += f"{status_icon} {h.target_name} - {dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if h.error:
            msg += f"   Error: {h.error}\n"
        msg += f"   Response: {h.response_time:.3f}s\n\n"
    
    await update.message.reply_text(msg)


# === Admin Commands ===

async def addsub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to add a subscription."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized. Admin only.")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addsub <chat_id>")
        return
    
    try:
        target_chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid chat_id. Must be an integer.")
        return
    
    await asyncio.to_thread(db.add_subscription, target_chat_id)
    await asyncio.to_thread(db.audit, update.effective_user.id, "add_subscription", f"Added {target_chat_id}")
    
    await update.message.reply_text(f"✅ Added subscription for chat_id: {target_chat_id}")
    logger.info(f"Admin {update.effective_user.id} added subscription for {target_chat_id}")


async def rmsub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to remove a subscription."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized. Admin only.")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /rmsub <chat_id>")
        return
    
    try:
        target_chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid chat_id. Must be an integer.")
        return
    
    await asyncio.to_thread(db.remove_subscription, target_chat_id)
    await asyncio.to_thread(db.audit, update.effective_user.id, "remove_subscription", f"Removed {target_chat_id}")
    
    await update.message.reply_text(f"✅ Removed subscription for chat_id: {target_chat_id}")
    logger.info(f"Admin {update.effective_user.id} removed subscription for {target_chat_id}")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to show bot statistics."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized. Admin only.")
        return
    
    # Get stats
    subs = await asyncio.to_thread(db.list_subscriptions)
    customers = await asyncio.to_thread(db.list_all_customers)
    
    total_targets = sum(len(c.targets) for c in customers)
    queue_stats = tele_queue.get_stats()
    queue_size = tele_queue.queue_size()
    
    msg = "📊 Bot Statistics\n\n"
    msg += f"Subscriptions: {len(subs)}\n"
    msg += f"Customers: {len(customers)}\n"
    msg += f"Total Targets: {total_targets}\n\n"
    msg += f"Queue Status:\n"
    msg += f"  Pending: {queue_size}\n"
    msg += f"  Sent: {queue_stats['sent']}\n"
    msg += f"  Failed: {queue_stats['failed']}\n"
    msg += f"  Dropped: {queue_stats['dropped']}\n"
    
    await update.message.reply_text(msg)


# === Background Workers ===

async def monitoring_worker() -> None:
    """
    Background task that orchestrates TCP checks for all customers.
    Runs continuously with configurable check intervals.
    """
    logger.info("Starting monitoring worker")
    
    semaphore = asyncio.Semaphore(config.get("max_concurrent_checks", 50))
    
    while True:
        try:
            # Get all subscribed chat_ids
            subscriptions = await asyncio.to_thread(db.list_subscriptions)
            
            # Ensure customer records exist for all subscriptions
            for chat_id in subscriptions:
                customer = await asyncio.to_thread(db.get_customer_by_chat, chat_id)
                if not customer:
                    # Create default customer config
                    await asyncio.to_thread(db.create_customer, chat_id)
                    logger.info(f"Created default customer config for chat_id {chat_id}")
            
            # Get all customers and run checks
            customers = await asyncio.to_thread(db.list_all_customers)
            
            if customers:
                check_tasks = []
                for customer in customers:
                    task = asyncio.create_task(
                        run_checks_for_customer(db, tele_queue, customer, semaphore, config)
                    )
                    check_tasks.append(task)
                
                # Wait for all checks to complete
                await asyncio.gather(*check_tasks, return_exceptions=True)
            
        except Exception:
            logger.exception("Error in monitoring worker")
        
        # Sleep before next round of checks
        await asyncio.sleep(5)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for the bot."""
    logger.error("Exception while handling an update:", exc_info=context.error)


# === Application Lifecycle ===

def setup_application() -> Application:
    """Initialize and configure the Telegram application."""
    token = config.get("telegram_token")
    if not token:
        logger.error("TELEGRAM_TOKEN is required but not set")
        sys.exit(1)
    
    # Build application
    app = Application.builder().token(token).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    
    # Admin commands
    app.add_handler(CommandHandler("addsub", addsub_cmd))
    app.add_handler(CommandHandler("rmsub", rmsub_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    # User target management commands
    app.add_handler(CommandHandler("addtarget", add_target_cmd))
    app.add_handler(CommandHandler("removetarget", remove_target_cmd))
    app.add_handler(CommandHandler("setinterval", set_interval_cmd))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    logger.info("Application configured successfully")
    return app


async def post_init(app: Application) -> None:
    """Called after application initialization, before polling starts."""
    global tele_queue, background_tasks
    
    # Create bot send wrapper
    async def bot_send(chat_id: int, text: str):
        await app.bot.send_message(chat_id=chat_id, text=text)
    
    # Initialize TeleQueue
    tele_queue = TeleQueue(
        bot_send,
        workers=config.get("tele_workers", 3),
        per_chat_rate_seconds=1.0
    )
    await tele_queue.start()
    
    # Start monitoring worker
    monitor_task = asyncio.create_task(monitoring_worker())
    background_tasks.append(monitor_task)
    
    # Start CPU benchmark monitor if enabled
    if config.get("cpu_benchmark", {}).get("enabled", False):
        admin_ids = config.get("admin_user_ids", [])
        benchmark_task = asyncio.create_task(
            benchmark_monitor_loop(db, tele_queue, config, admin_ids)
        )
        background_tasks.append(benchmark_task)
    
    logger.info("Background tasks started")


async def post_shutdown(app: Application) -> None:
    """Called during shutdown to cleanup resources."""
    global tele_queue, background_tasks
    
    logger.info("Shutting down gracefully...")
    
    # Stop TeleQueue
    if tele_queue:
        await tele_queue.stop()
    
    # Cancel background tasks
    for task in background_tasks:
        task.cancel()
    
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
    
    background_tasks.clear()
    logger.info("Shutdown complete")


def main() -> None:
    """Main entry point."""
    global config, db, application
    
    # Load configuration
    logger.info("Loading configuration...")
    config = load_config()
    
    # Initialize database
    logger.info("Initializing database...")
    db = DB(config.get("db_url"))
    
    # Setup application
    application = setup_application()
    
    # Register lifecycle hooks
    application.post_init = post_init
    application.post_shutdown = post_shutdown
    
    # Run the bot
    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()