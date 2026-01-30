import asyncio
import os
import logging
import html
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from .middleware import AuthMiddleware
from ..engine.logic import Alert
from ..services.remnawave import RemnawaveClient
from ..services.monitor import SystemMonitor

class TelegramBot:
    # Interaction Presets
    CONFIG_PRESETS = {
        "users": [1, 3, 5, 10, 20],
        "speed": [10, 50, 100, 500, 1000],
        "efficiency": [1, 5, 10, 20, 50]
    }
    CONFIG_UNITS = {
        "users": "",
        "speed": " KB/s",
        "efficiency": " KB/s/user"
    }

    def __init__(self, remnawave_client: RemnawaveClient, health_service):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.admin_ids = os.getenv("ADMIN_IDS", "").split(",")
        if not self.token:
             logging.error("TELEGRAM_BOT_TOKEN is not set")
             return

        self.bot = Bot(token=self.token)
        self.dp = Dispatcher()
        self.dp.message.middleware(AuthMiddleware())
        self.remnawave = remnawave_client
        self.health_service = health_service
        self.monitor = SystemMonitor()

        # Register commands
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_help, Command("help"))
        self.dp.message.register(self.cmd_status, Command("status"))
        self.dp.message.register(self.cmd_nodes, Command("nodes"))
        self.dp.message.register(self.cmd_config, Command("config"))
        self.dp.message.register(self.cmd_alerts, Command("alerts"))
        self.dp.message.register(self.cmd_reports, Command("reports"))
        self.dp.message.register(self.cmd_top, Command("top"))
        
        # Register Callbacks
        self.dp.callback_query.register(self.process_config_callback, lambda c: c.data and c.data.startswith("cfg_"))

    async def start(self):
        await self.dp.start_polling(self.bot)

    async def send_alert(self, alert: Alert):
        node_name = os.getenv("NODE_NAME", "Unknown Node")
        emoji_map = {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "INFO": "ℹ️"
        }
        emoji = emoji_map.get(alert.level, "ℹ️")
        
        message = f"{emoji} *{alert.message}*\n"
        message += f"🌍 *Node*: {node_name}\n"
        if alert.metadata:
            for k, v in alert.metadata.items():
                message += f"*{k.capitalize()}*: {v}\n"
        
        # Broadcast to all admins (Parallel)

        tasks = []
        for admin_id in self.admin_ids:
            if admin_id:
                tasks.append(self.send_safe_message(admin_id, message))
        
        await asyncio.gather(*tasks)

    async def send_safe_message(self, chat_id: int, text: str):
        """Helper to send message with retry logic."""
        for attempt in range(3):
            try:
                await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
                return
            except Exception as e:
                err = str(e)
                if attempt == 2:
                     logging.error(f"Failed to send alert to {chat_id}: {err}")
                else:
                     logging.warning(f"Retry {attempt+1}/3 for {chat_id}: {err}")
                     await asyncio.sleep(1)

    async def generate_status_text(self) -> str:
        stats = self.monitor.get_system_stats()
        
        # Check API & Cluster Size
        api_ok = await self.remnawave.check_connectivity()
        api_status = "✅ Online" if api_ok else "❌ Unreachable"
        
        cluster_size = 0
        try:
             nodes = await self.remnawave.get_nodes()
             cluster_size = len(nodes)
        except:
             pass

        msg = f"🛡️ <b>RemnaGuard Central</b>\n"
        msg += f"🌐 <b>API Connection</b>: {api_status}\n"
        msg += f"🔭 <b>Monitored Nodes</b>: {cluster_size}\n"
        msg += f"-----------------------------\n"
        msg += f"💻 <b>Master Host</b>: <code>{html.escape(stats['hostname'])}</code>\n"
        msg += f"🧠 <b>CPU</b>: {stats['cpu_percent']}%\n"
        msg += f"💾 <b>RAM</b>: {stats['memory_percent']}%\n"
        return msg

    async def send_status_report(self, title: str = None):
        """Sends a status report to all admins (used for Heartbeats)."""
        text = await self.generate_status_text()
        if title:
            text = f"<b>{title}</b>\n\n{text}"
            
        for admin_id in self.admin_ids:
            if admin_id:
                try:
                    await self.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Failed to send status to {admin_id}: {e}")

    # Commands
    async def cmd_start(self, message: types.Message):
        await message.answer(
            "🛡️ <b>RemnaGuard Central</b>\n"
            "Monitoring your entire cluster via API.\n\n"
            "/status - Cluster Health & Stats\n"
            "/nodes - List All Nodes\n",
            parse_mode="HTML"
        )
    async def cmd_help(self, message: types.Message):
        help_text = (
            "🛡️ <b>RemnaGuard Help</b>\n\n"
            "<b>Monitoring</b>\n"
            "/status - System & API Health\n"
            "/nodes - Node List & Bandwidth\n"
            "/top - Top Nodes by Load\n"
            "/alerts - Recent History\n"
            "/reports - Silent Incidents\n\n"
            "<b>Configuration</b>\n"
            "/config - View/Edit Thresholds\n"
            "<i>(Usage: /config set users 5)</i>"
        )
        await message.answer(help_text, parse_mode="HTML")

    async def cmd_nodes(self, message: types.Message):
        """Fetch and display all nodes."""
        await message.answer("🔄 Fetching node list...")
        try:
            nodes = await self.remnawave.get_nodes()
            if not nodes:
                await message.answer("⚠️ No nodes found in API.")
                return

            msg = f"🌍 <b>Cluster Nodes ({len(nodes)})</b>\n\n"
            
            for node in nodes:
                # Extract details safely
                name = node.get("name", "Unknown")
                
                # Status Logic
                is_connected = node.get("isConnected", False)
                status_raw = node.get("status", "Unknown")
                
                if is_connected or str(status_raw).lower() in ["connected", "online", "active", "true"]:
                     status_icon = "🟢"
                     status_text = "Online"
                else:
                     status_icon = "🔴"
                     status_text = "Offline"
                
                users = node.get("usersOnline") or node.get("online_users") or 0
                
                msg += f"{status_icon} <b>{html.escape(name)}</b>\n"
                msg += f"   👥 Users: {users} | 🚦 Status: {status_text}\n\n"
            
            await message.answer(msg, parse_mode="HTML")
        except Exception as e:
            logging.error(f"cmd_nodes failed: {e}")
            await message.answer(f"❌ Failed to fetch nodes: {e}")

    async def cmd_status(self, message: types.Message):
        msg = await self.generate_status_text()
        await message.answer(msg, parse_mode="HTML")

    async def cmd_config(self, message: types.Message):
        """View or Edit detection thresholds (Interactive)."""
        await self.send_config_menu(message)

    async def send_config_menu(self, message: types.Message, is_edit=False):
        cfg = self.health_service.get_config()
        
        text = (
            "⚙️ <b>Detection Configuration</b>\n\n"
            f"👥 <b>Min Users</b>: {cfg['min_users']}\n"
            f"🚀 <b>Min Speed</b>: {cfg['min_speed']} KB/s\n"
            f"🐌 <b>Efficiency</b>: {cfg['min_efficiency']} KB/s/user\n\n"
            "<i>Select a parameter to edit:</i>"
        )
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="👥 Edit Min Users", callback_data="cfg_edit:users"),
                types.InlineKeyboardButton(text="🚀 Edit Speed", callback_data="cfg_edit:speed")
            ],
            [
                types.InlineKeyboardButton(text="🐌 Edit Efficiency", callback_data="cfg_edit:efficiency")
            ],
            [
                types.InlineKeyboardButton(text="🔄 Refresh", callback_data="cfg_home")
            ]
        ])
        
        try:
            if is_edit:
                await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            else:
                await message.answer(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            # Ignore MessageNotModified or other edit errors
            logging.warning(f"Config menu update skipped: {e}")

    async def process_config_callback(self, callback: types.CallbackQuery):
        action, *args = callback.data.split(":")
        
        try:
            if action == "cfg_home":
                await self.send_config_menu(callback.message, is_edit=True)
                await callback.answer("Refreshed")
                
            elif action == "cfg_edit":
                key = args[0]
                text = f"📝 <b>Edit {key.capitalize()}</b>\nSelect a new threshold:"
                
                buttons = []
                row = []
                # Use Class Constants
                presets = self.CONFIG_PRESETS.get(key, [])
                unit = self.CONFIG_UNITS.get(key, "")
                
                for val in presets:
                    btn_text = f"{val}{unit}"
                    row.append(types.InlineKeyboardButton(text=btn_text, callback_data=f"cfg_set:{key}:{val}"))
                    if len(row) == 3:
                         buttons.append(row)
                         row = []
                if row: buttons.append(row)
                
                buttons.append([types.InlineKeyboardButton(text="🔙 Back", callback_data="cfg_home")])
                
                await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
                await callback.answer()
                
            elif action == "cfg_set":
                key = args[0]
                val = int(args[1])
                
                if self.health_service.update_config(key, val):
                    await callback.answer(f"✅ {key} set to {val}!")
                    await self.send_config_menu(callback.message, is_edit=True)
                else:
                    await callback.answer("❌ Failed to update.", show_alert=True)
        except Exception as e:
            logging.error(f"Config callback error: {e}")
            await callback.answer("❌ Error occurred.")

    async def cmd_top(self, message: types.Message):
        """Show top nodes by users."""
        await message.answer("📊 Calculating top nodes...")
        try:
             nodes = await self.remnawave.get_nodes()
             # Sort by active users desc
             nodes.sort(key=lambda x: int(x.get("usersOnline") or x.get("online_users") or 0), reverse=True)
             
             msg = "🏆 <b>Top Nodes (By Users)</b>\n\n"
             for i, node in enumerate(nodes[:5], 1):
                 name = node.get("name", "Unknown")
                 users = int(node.get("usersOnline") or node.get("online_users") or 0)
                 msg += f"{i}. <b>{name}</b>: {users} users\n"
             
             await message.answer(msg, parse_mode="HTML")
        except Exception as e:
             await message.answer(f"❌ Failed: {e}")

    async def cmd_alerts(self, message: types.Message):
        """Show recent alerts."""
        alerts = self.health_service.get_recent_alerts()
        if not alerts:
            await message.answer("✅ No recent alerts.")
            return

    async def cmd_reports(self, message: types.Message):
        """Show silent incident history."""
        history = self.health_service.get_incident_history()
        if not history:
             await message.answer("📋 No silent incidents recorded recently.")
             return
             
        msg = "📋 <b>Incident Report (Last 50)</b>\n\n"
        for h in reversed(history):
            msg += f"• <b>{h['node']}</b>: {h['issue']} ({h['status']})\n"
            msg += f"   Duration: {h['duration']} | Max Users: {h['max_users']}\n\n"
            
        await message.answer(msg, parse_mode="HTML")
