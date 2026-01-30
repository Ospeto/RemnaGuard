import asyncio
import os
import logging
from .services.remnawave import RemnawaveClient
from .bot.main import TelegramBot

# Configuration
# Cleaned up config
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL)

async def heartbeat_loop(bot: TelegramBot):
    """Sends periodic status reports (Heartbeats)."""
    # 1. Startup Notification
    try:
        logging.info("Sending Startup Notification...")
        await bot.send_status_report(title="🚀 RemnaGuard Online")
    except Exception as e:
        logging.error(f"Failed to send startup msg: {e}")

    # 2. Periodic Loop
    interval = int(os.getenv("HEARTBEAT_INTERVAL", "21600")) # Default 6 hours
    if interval <= 0:
        logging.info("Heartbeat disabled.")
        return

    logging.info(f"Starting Heartbeat Loop (Interval: {interval}s)")
    while True:
        await asyncio.sleep(interval)
        try:
            await bot.send_status_report(title="💓 System Heartbeat")
        except Exception as e:
            logging.error(f"Heartbeat failed: {e}")

async def cluster_loop(service: 'ClusterHealthService', bot: TelegramBot):
    """Monitors the health of the entire cluster via API."""
    logging.info("Starting Centralized Cluster Sentinel...")
    while True:
        try:
            alerts = await service.check_cluster()
            for alert in alerts:
                logging.warning(f"CLUSTER ALERT: {alert.message}")
                await bot.send_alert(alert)
        except Exception as e:
            logging.error(f"Cluster sentinel error: {e}")
            
        await asyncio.sleep(30) # Check every 30s

async def main():
    # Initialize Services
    remnawave = RemnawaveClient()
    from .engine.logic import ClusterHealthService
    health_service = ClusterHealthService(remnawave)
    
    # Pass health_service to bot for config/stats access
    bot = TelegramBot(remnawave, health_service)
    
    # Start Tasks
    logging.info("Starting Remnawave Guard (Centralized API Mode)...")
    
    asyncio.create_task(heartbeat_loop(bot))
    asyncio.create_task(cluster_loop(health_service, bot))
    
    # Start Bot (this will block main thread)
    logging.info("Starting Telegram Bot...")
    
    # Start Bot
    try:
        if bot.bot:
            logging.info("Bot Mode: POLLING (Monitor Instance)")
            # Delete webhook to be safe (if switching from webhook mode)
            await bot.bot.delete_webhook(drop_pending_updates=True)
            await bot.dp.start_polling(bot.bot)
        else:
             logging.error("Bot not initialized properly")
             while True:
                 await asyncio.sleep(3600)
    except Exception as e:
        logging.error(f"Bot crashed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
