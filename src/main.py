import asyncio
import os
import logging
from dotenv import load_dotenv

# Load env vars from .env if available
load_dotenv()
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

async def digest_loop(health_service: 'ClusterHealthService', bot: TelegramBot):
    """Send daily digest at midnight."""
    import time
    digest_hour = int(os.getenv("DIGEST_HOUR", "0"))  # Default midnight
    
    while True:
        # Calculate time until next digest
        now = time.localtime()
        current_hour = now.tm_hour
        current_min = now.tm_min
        
        # Check if it's digest time (within first 5 minutes of the hour)
        if current_hour == digest_hour and current_min < 5:
            try:
                stats = health_service.db.get_today_stats()
                
                msg = (
                    "📊 <b>Daily Digest</b>\n\n"
                    f"📅 <b>Date</b>: {time.strftime('%Y-%m-%d')}\n"
                    f"🚨 <b>Incidents</b>: {stats['incidents']}\n"
                    f"👥 <b>Peak Users</b>: {stats['peak_users']} (<b>{stats['peak_node']}</b>)\n"
                    f"⚡ <b>Avg Efficiency</b>: {stats['avg_efficiency']:.2f} KB/s/user\n\n"
                    "Good night! 🌙"
                )
                
                # Send to all admins
                for admin_id in bot.admin_ids:
                    if admin_id:
                        try:
                            await bot.bot.send_message(chat_id=admin_id, text=msg, parse_mode="HTML")
                        except Exception as e:
                            logging.error(f"Failed to send digest to {admin_id}: {e}")
                
                logging.info("Daily digest sent!")
                
                # Save to database for history
                health_service.db.save_daily_stats(
                    time.strftime('%Y-%m-%d'),
                    stats['incidents'],
                    0,  # alerts count (could track this later)
                    stats['peak_users'],
                    stats['peak_node'],
                    stats['avg_efficiency']
                )
                
                # Wait until next hour to avoid duplicate sends
                await asyncio.sleep(3600)
            except Exception as e:
                logging.error(f"Digest error: {e}")
        
        # Check every 5 minutes
        await asyncio.sleep(300)

async def smart_baseline_loop(health_service: 'ClusterHealthService'):
    """Update AI Smart Baselines 4 times a day (every 6 hours)."""
    import time
    
    # Schedule: 0, 6, 12, 18 hours
    target_hours = [0, 6, 12, 18]
    
    while True:
        now = time.localtime()
        current_hour = now.tm_hour
        current_min = now.tm_min
        
        # Run in the first 5 mins of target hours
        if current_hour in target_hours and current_min < 5:
            logging.info("Starting scheduled AI Smart Baseline update...")
            await health_service.update_smart_baselines()
            # Sleep for an hour to avoid re-triggering
            await asyncio.sleep(3600)
            
        # Check every 5 mins
        await asyncio.sleep(300)

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
    asyncio.create_task(digest_loop(health_service, bot))
    asyncio.create_task(smart_baseline_loop(health_service))
    
    # PHASE 15: Immediate Startup Sync
    if health_service.cf.enabled:
        logging.info("Triggering initial DNS Sync...")
        # We run it in a task so it doesn't block bot startup
        asyncio.create_task(health_service.check_cluster())
    
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
