import asyncio
import os
import logging
import html
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
        self.dp.message.register(self.cmd_graph, Command("graph"))
        self.dp.message.register(self.cmd_node, Command("node"))
        self.dp.message.register(self.cmd_uptime, Command("uptime"))
        self.dp.message.register(self.cmd_digest, Command("digest"))
        self.dp.message.register(self.cmd_analyze, Command("analyze"))
        self.dp.message.register(self.cmd_ai_model, Command("ai_model"))
        self.dp.message.register(self.cmd_export, Command("export"))
        self.dp.message.register(self.cmd_dns_status, Command("dns_status"))
        self.dp.message.register(self.cmd_dns_sync, Command("dns_sync"))
        self.dp.message.register(self.cmd_dns_sync, Command("dns_rotate"))
        
        # Register Callbacks
        self.dp.callback_query.register(self.process_config_callback, lambda c: c.data and c.data.startswith("cfg_"))
        self.dp.callback_query.register(self.process_menu_callback, lambda c: c.data and c.data.startswith("menu_"))
        self.dp.callback_query.register(self.process_node_callback, lambda c: c.data and c.data.startswith("node_"))
        self.dp.callback_query.register(self.process_model_callback, lambda c: c.data and c.data.startswith("model_"))
        self.dp.callback_query.register(self.process_feedback_callback, lambda c: c.data and c.data.startswith("ai_fb:"))
        self.dp.callback_query.register(self.process_approval_callback, lambda c: c.data and c.data.startswith("ai_app:"))

    async def start(self):
        await self.dp.start_polling(self.bot)

    async def send_alert(self, alert: Alert):
        node_name = alert.metadata.get("node", "Unknown")
        emoji_map = {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "INFO": "ℹ️"
        }
        emoji = emoji_map.get(alert.level, "ℹ️")
        
        # Check if this is an Incident approval request
        # We look at metadata for 'incident_state'
        is_approval_req = alert.metadata.get("state") == "AWAIT_APPROVAL"
        
        message = f"{emoji} *{alert.message}*\n"
        if is_approval_req:
            message = f"🛡️ **DNS APPROVAL REQUIRED**\nAI detected an incident on {node_name} and is waiting for your decision.\n\n"
        
        message += f"🌍 *Node*: {node_name}\n"
        if alert.metadata:
            for k, v in alert.metadata.items():
                if k not in ["node", "state"]: # Skip these in body
                    message += f"*{k.capitalize()}*: {v}\n"
        
        # Reply Markup for Approvals
        reply_markup = None
        if is_approval_req:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Approve (Drop DNS)", callback_data=f"ai_app:CONFIRM:{node_name}"),
                    InlineKeyboardButton(text="❌ Reject (Keep DNS)", callback_data=f"ai_app:REJECT:{node_name}")
                ]
            ])
        
        # Broadcast to all admins (Parallel)
        tasks = []
        for admin_id in self.admin_ids:
            if admin_id:
                tasks.append(self.send_safe_message(admin_id, message, reply_markup=reply_markup))
        
        await asyncio.gather(*tasks)

    async def send_safe_message(self, chat_id: int, text: str, reply_markup=None):
        """Helper to send message with retry logic."""
        for attempt in range(3):
            try:
                await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=reply_markup)
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
        """Main menu with interactive buttons."""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Status", callback_data="menu_status"),
                InlineKeyboardButton(text="🖥️ Nodes", callback_data="menu_nodes")
            ],
            [
                InlineKeyboardButton(text="📈 Graph", callback_data="menu_graph"),
                InlineKeyboardButton(text="🔝 Top", callback_data="menu_top")
            ],
            [
                InlineKeyboardButton(text="📉 Uptime", callback_data="menu_uptime"),
                InlineKeyboardButton(text="📊 Digest", callback_data="menu_digest")
            ],
            [
                InlineKeyboardButton(text="⚙️ Config", callback_data="menu_config"),
                InlineKeyboardButton(text="🧠 AI", callback_data="menu_ai_model")
            ],
            [
                InlineKeyboardButton(text="❓ Help", callback_data="menu_help")
            ]
        ])
        
        await message.answer(
            "🛡️ <b>RemnaGuard Central</b>\n"
            "Monitoring your entire cluster via API.\n\n"
            "Select an option below:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    async def cmd_help(self, message: types.Message):
        help_text = (
            "🛡️ <b>RemnaGuard Help</b>\n\n"
            "<b>📊 Monitoring</b>\n"
            "/status - System & API Health\n"
            "/nodes - Node List & Bandwidth\n"
            "/top - Top Nodes by Load\n"
            "/graph - 6-Hour Efficiency Chart\n"
            "/node &lt;name&gt; - Deep Dive Stats\n\n"
            "<b>🧠 AI Insights</b>\n"
            "/analyze &lt;name&gt; - AI Performance Analysis\n"
            "/ai_model - Switch Gemini Models\n\n"
            "<b>📈 Analytics</b>\n"
            "/uptime - 7-Day Uptime Stats\n"
            "/digest - Today's Summary\n"
            "/alerts - Recent Alerts\n"
            "/reports - Silent Incidents\n\n"
            "<b>⚙️ Configuration</b>\n"
            "/config - View/Edit Thresholds\n"
            "/export - Download Database Backup\n\n"
            "<i>Tip: Use /start for button menu!</i>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
        ])
        await message.answer(help_text, parse_mode="HTML", reply_markup=keyboard)

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

    async def cmd_graph(self, message: types.Message):
        """Show efficiency sparklines for all nodes."""
        node_names = self.health_service.get_all_node_names()
        
        if not node_names:
            await message.answer("⏳ No data yet. Please wait a few minutes for data collection.")
            return
        
        msg = "📊 <b>6-Hour Efficiency Chart</b>\n\n"
        
        for name in sorted(node_names):
            history = self.health_service.get_node_history(name)
            if history:
                sparkline = history.get_sparkline(hours=6)
                trend = history.get_trend()
                
                trend_emoji = {
                    "UP": "📈",
                    "DOWN": "📉",
                    "STABLE": "➡️",
                    "UNKNOWN": "❓"
                }.get(trend["direction"], "❓")
                
                msg += f"<b>{name}</b>\n"
                msg += f"{sparkline} {trend_emoji} ({trend['change_pct']:+.1f}%)\n\n"
        
        await message.answer(msg, parse_mode="HTML")

    async def cmd_node(self, message: types.Message):
        """Deep dive into a specific node."""
        # Parse node name from command
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "Usage: <code>/node Node-Name</code>\n\n"
                "Available nodes:\n" + 
                "\n".join(f"• {n}" for n in self.health_service.get_all_node_names()),
                parse_mode="HTML"
            )
            return
        
        node_name = parts[1].strip()
        history = self.health_service.get_node_history(node_name)
        
        if not history:
            await message.answer(f"❌ Node '{node_name}' not found or no data yet.")
            return
        
        # Get latest sample
        if history.samples:
            latest = history.samples[-1]
            speed = latest["speed"]
            users = latest["users"]
            eff = latest["eff"]
        else:
            speed = users = eff = 0
        
        # Get stats
        trend = history.get_trend()
        baseline = history.get_baseline()
        sparkline = history.get_sparkline(hours=6)
        
        trend_emoji = {"UP": "📈", "DOWN": "📉", "STABLE": "➡️", "UNKNOWN": "❓"}.get(trend["direction"], "❓")
        
        # Check for active incident
        incident = self.health_service.active_incidents.get(node_name)
        incident_text = "None" if not incident else f"⚠️ {incident.issue_type} ({incident.state})"
        
        import time as time_module
        current_hour = int(time_module.strftime("%H"))
        
        msg = (
            f"📍 <b>Node: {node_name}</b>\n\n"
            f"<b>Current Status</b>\n"
            f"Users: {users} | Speed: {speed:.1f} KB/s\n"
            f"Efficiency: {eff:.1f} KB/s/user\n\n"
            f"<b>Trend (30 min)</b>: {trend_emoji} {trend['change_pct']:+.1f}%\n"
            f"<b>Baseline (Hour {current_hour})</b>: {baseline:.1f} KB/s/user\n"
            f"<b>Active Incident</b>: {incident_text}\n\n"
            f"<b>Last 6 Hours</b>\n"
            f"{sparkline}"
        )
        
        # Add back button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Nodes", callback_data="menu_nodes")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
        ])
        
        await message.answer(msg, parse_mode="HTML", reply_markup=keyboard)

    # === CALLBACK HANDLERS ===
    
    async def process_menu_callback(self, callback: types.CallbackQuery):
        """Handle main menu button presses."""
        action = callback.data.replace("menu_", "")
        
        if action == "main":
            # Show main menu
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Status", callback_data="menu_status"),
                    InlineKeyboardButton(text="🖥️ Nodes", callback_data="menu_nodes")
                ],
                [
                    InlineKeyboardButton(text="📈 Graph", callback_data="menu_graph"),
                    InlineKeyboardButton(text="🔝 Top", callback_data="menu_top")
                ],
                [
                    InlineKeyboardButton(text="🚨 Alerts", callback_data="menu_alerts"),
                    InlineKeyboardButton(text="📋 Reports", callback_data="menu_reports")
                ],
                [
                    InlineKeyboardButton(text="⚙️ Config", callback_data="menu_config"),
                    InlineKeyboardButton(text="❓ Help", callback_data="menu_help")
                ]
            ])
            await callback.message.edit_text(
                "🛡️ <b>RemnaGuard Central</b>\n"
                "Monitoring your entire cluster via API.\n\n"
                "Select an option below:",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
        elif action == "status":
            text = await self.generate_status_text()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_status")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            
        elif action == "nodes":
            # Show node list with buttons
            node_names = self.health_service.get_all_node_names()
            if not node_names:
                await callback.message.edit_text(
                    "⏳ No nodes tracked yet. Wait for first check.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
                    ])
                )
            else:
                buttons = []
                for name in sorted(node_names):
                    buttons.append([InlineKeyboardButton(text=f"📍 {name}", callback_data=f"node_{name}")])
                buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")])
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                await callback.message.edit_text(
                    "🖥️ <b>Select a Node</b>",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                
        elif action == "graph":
            node_names = self.health_service.get_all_node_names()
            if not node_names:
                msg = "⏳ No data yet. Please wait a few minutes for data collection."
            else:
                msg = "📊 <b>6-Hour Efficiency Chart</b>\n\n"
                for name in sorted(node_names):
                    history = self.health_service.get_node_history(name)
                    if history:
                        sparkline = history.get_sparkline(hours=6)
                        trend = history.get_trend()
                        trend_emoji = {"UP": "📈", "DOWN": "📉", "STABLE": "➡️", "UNKNOWN": "❓"}.get(trend["direction"], "❓")
                        msg += f"<b>{name}</b>\n{sparkline} {trend_emoji} ({trend['change_pct']:+.1f}%)\n\n"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_graph")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
            
        elif action == "top":
            nodes = await self.remnawave.get_nodes()
            if not nodes:
                msg = "⚠️ No nodes found."
            else:
                sorted_nodes = sorted(nodes, key=lambda n: int(n.get("usersOnline") or 0), reverse=True)[:5]
                msg = "🔝 <b>Top 5 Nodes by Load</b>\n\n"
                for i, node in enumerate(sorted_nodes, 1):
                    name = node.get("name", "Unknown")
                    users = int(node.get("usersOnline") or 0)
                    msg += f"{i}. <b>{name}</b>: {users} users\n"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_top")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
            
        elif action == "alerts":
            alerts = self.health_service.get_recent_alerts()
            if not alerts:
                msg = "✅ No recent alerts."
            else:
                msg = "🚨 <b>Recent Alerts</b>\n\n"
                for alert in alerts[-10:]:
                    msg += f"• {alert}\n"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
            
        elif action == "reports":
            history = self.health_service.get_incident_history()
            if not history:
                msg = "📋 No silent incidents recorded recently."
            else:
                msg = "📋 <b>Incident Report (Last 50)</b>\n\n"
                for h in history[:10]:  # Show last 10
                    msg += f"• <b>{h.get('node', 'Unknown')}</b>: {h.get('issue', 'Unknown')}\n"
                    msg += f"   Duration: {h.get('duration', 'N/A')} | Status: {h.get('status', 'N/A')}\n\n"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
            
        elif action == "config":
            config = self.health_service.get_config()
            msg = (
                "⚙️ <b>Current Configuration</b>\n\n"
                f"• <b>Min Users</b>: {config['min_users']}\n"
                f"• <b>Min Speed</b>: {config['min_speed']} KB/s\n"
                f"• <b>Min Efficiency</b>: {config['min_efficiency']} KB/s/user\n\n"
                "Use /config set [key] [value] to change."
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
            
        elif action == "help":
            msg = (
                "🛡️ <b>RemnaGuard Help</b>\n\n"
                "<b>📊 Monitoring</b>\n"
                "<b>Status</b> - System & API Health\n"
                "<b>Nodes</b> - Node List & Bandwidth\n"
                "<b>Top</b> - Busiest nodes\n"
                "<b>Graph</b> - 6-Hour efficiency sparklines\n\n"
                "<b>📈 Analytics</b>\n"
                "<b>Uptime</b> - 7-Day Stats\n"
                "<b>Digest</b> - Today's Summary\n"
                "<b>Alerts</b> - Recent Alerts\n"
                "<b>Reports</b> - Silent Incidents\n\n"
                "<b>⚙️ Configuration</b>\n"
                "<b>Config</b> - View/Edit Thresholds"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
        
        elif action == "uptime":
            uptimes = self.health_service.db.get_all_uptimes(days=7)
            
            if not uptimes:
                msg = "⏳ No uptime data yet. Check back after nodes have been tracked for a while."
            else:
                msg = "📈 <b>7-Day Uptime</b>\n\n"
                for node, uptime in sorted(uptimes.items(), key=lambda x: x[1], reverse=True):
                    if uptime >= 99:
                        emoji = "🟢"
                    elif uptime >= 95:
                        emoji = "🟡"
                    else:
                        emoji = "🔴"
                    msg += f"{emoji} <b>{node}</b>: {uptime:.2f}%\n"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_uptime")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
        
        elif action == "digest":
            stats = self.health_service.db.get_today_stats()
            msg = (
                "📊 <b>Today's Digest</b>\n\n"
                f"🚨 <b>Incidents</b>: {stats['incidents']}\n"
                f"👥 <b>Peak Users</b>: {stats['peak_users']} (<b>{stats['peak_node']}</b>)\n"
                f"⚡ <b>Avg Efficiency</b>: {stats['avg_efficiency']:.2f} KB/s/user\n"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_digest")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
            ])
            await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
        
        elif action == "ai_model":
            await self.cmd_ai_model(callback.message)
            return

        await callback.answer()

    async def process_node_callback(self, callback: types.CallbackQuery):
        """Handle node selection button presses."""
        node_name = callback.data.replace("node_", "")
        history = self.health_service.get_node_history(node_name)
        
        if not history:
            await callback.answer(f"Node '{node_name}' not found!", show_alert=True)
            return
        
        # Get latest sample
        if history.samples:
            latest = history.samples[-1]
            speed = latest["speed"]
            users = latest["users"]
            eff = latest["eff"]
        else:
            speed = users = eff = 0
        
        # Get stats
        trend = history.get_trend()
        baseline = history.get_baseline()
        sparkline = history.get_sparkline(hours=6)
        
        import time as time_module
        current_hour = int(time_module.strftime("%H"))
        trend_emoji = {"UP": "📈", "DOWN": "📉", "STABLE": "➡️", "UNKNOWN": "❓"}.get(trend["direction"], "❓")
        
        # Check for active incident
        incident = self.health_service.active_incidents.get(node_name)
        incident_text = "None" if not incident else f"⚠️ {incident.issue_type} ({incident.state})"
        
        msg = (
            f"📍 <b>Node: {node_name}</b>\n\n"
            f"<b>Current Status</b>\n"
            f"Users: {users} | Speed: {speed:.1f} KB/s\n"
            f"Efficiency: {eff:.1f} KB/s/user\n\n"
            f"<b>Trend (30 min)</b>: {trend_emoji} {trend['change_pct']:+.1f}%\n"
            f"<b>Baseline (Hour {current_hour})</b>: {baseline:.1f} KB/s/user\n"
            f"<b>Active Incident</b>: {incident_text}\n\n"
            f"<b>Last 6 Hours</b>\n"
            f"{sparkline}"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"node_{node_name}")],
            [InlineKeyboardButton(text="⬅️ Back to Nodes", callback_data="menu_nodes")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
        ])
        
        await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    # === NEW COMMANDS ===
    
    async def cmd_uptime(self, message: types.Message):
        """Show 7-day uptime for all nodes."""
        uptimes = self.health_service.db.get_all_uptimes(days=7)
        
        if not uptimes:
            await message.answer("⏳ No uptime data yet. Check back after nodes have been tracked for a while.")
            return
        
        msg = "📈 <b>7-Day Uptime</b>\n\n"
        for node, uptime in sorted(uptimes.items(), key=lambda x: x[1], reverse=True):
            # Color based on uptime
            if uptime >= 99:
                emoji = "🟢"
            elif uptime >= 95:
                emoji = "🟡"
            else:
                emoji = "🔴"
            msg += f"{emoji} <b>{node}</b>: {uptime:.2f}%\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_uptime")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
        ])
        await message.answer(msg, parse_mode="HTML", reply_markup=keyboard)
    
    async def cmd_digest(self, message: types.Message):
        """Show today's digest summary."""
        stats = self.health_service.db.get_today_stats()
        
        msg = (
            "📊 <b>Today's Digest</b>\n\n"
            f"🚨 <b>Incidents</b>: {stats['incidents']}\n"
            f"👥 <b>Peak Users</b>: {stats['peak_users']} (<b>{stats['peak_node']}</b>)\n"
            f"⚡ <b>Avg Efficiency</b>: {stats['avg_efficiency']:.2f} KB/s/user\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_digest")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_main")]
        ])
        await message.answer(msg, parse_mode="HTML", reply_markup=keyboard)

    async def cmd_analyze(self, message: types.Message):
        """Ask AI to analyze a specific node."""
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            # Show list of nodes to analyze
            node_names = self.health_service.get_all_node_names()
            msg = "🧠 <b>AI Analysis</b>\nUsage: <code>/analyze [node_name]</code>\n\nAvailable Nodes:\n"
            for name in sorted(node_names):
                msg += f"• <code>{name}</code>\n"
            await message.answer(msg, parse_mode="HTML")
            return
            
        node_name = args[1]
        history = self.health_service.get_node_history(node_name)
        if not history:
             await message.answer(f"⚠️ Node '{node_name}' not found or no history available.")
             return
             
        # Notify user (since AI can be slow)
        processing_msg = await message.answer(f"🧠 Asking Gemini AI to analyze <b>{node_name}</b>...")
        await self.bot.send_chat_action(message.chat.id, "typing")
        
        # Get history as list of dicts
        history_data = list(history.samples)[-50:] # Last 50 samples
        
        # Call AI with negative examples
        neg_examples = self.health_service.db.get_negative_examples()
        analysis = await self.health_service.ai.analyze_node(node_name, history_data, neg_examples)
        
        # Format response
        msg = f"🧠 <b>AI Analysis: {node_name}</b>\n\n{analysis}"
        
        # Add feedback buttons
        # format: feedback:rating:node_name (truncate verdict since it's in msg)
        # We need a way to store context. For now, we'll store basic context in callback data
        # actually, callback data is limited to 64 bytes. We will use a temporary cache or just simple rating.
        # Let's simple rating: feedback:ACCURATE:node_name or feedback:WRONG:node_name
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👍 Accurate", callback_data=f"ai_fb:ACCURATE:{node_name}"),
                InlineKeyboardButton(text="👎 Wrong", callback_data=f"ai_fb:WRONG:{node_name}")
            ]
        ])
        
        await processing_msg.edit_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    async def cmd_ai_model(self, message: types.Message):
        """Show menu to switch AI models."""
        current_model = self.health_service.ai.current_model_name
        
        msg = (
            f"🧠 <b>Gemini Model Selector</b>\n\n"
            f"Current Model: <code>{current_model}</code>\n\n"
            "Select a model to switch:"
        )
        
        # Build keyboard from available models in AIService
        buttons = []
        for model_id, model_name in self.health_service.ai.AVAILABLE_MODELS.items():
            prefix = "✅ " if model_id == current_model else ""
            buttons.append([InlineKeyboardButton(text=f"{prefix}{model_name}", callback_data=f"model_{model_id}")])
            
        buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="model_cancel")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(msg, parse_mode="HTML", reply_markup=keyboard)

    async def process_model_callback(self, callback: types.CallbackQuery):
        """Handle model switching callback."""
        action = callback.data.split("_", 1)[1] # remove model_ prefix
        
        if action == "cancel":
            await callback.message.delete()
            return
            
        model_id = action
        success = self.health_service.ai.set_model(model_id)
        
        # Re-render menu to show checkmark
        current_model = self.health_service.ai.current_model_name
        msg = (
            f"🧠 <b>Gemini Model Selector</b>\n\n"
            f"Current Model: <code>{current_model}</code>\n\n"
            "Select a model to switch:"
        )
        buttons = []
        for mid, mname in self.health_service.ai.AVAILABLE_MODELS.items():
            prefix = "✅ " if mid == current_model else ""
            buttons.append([InlineKeyboardButton(text=f"{prefix}{mname}", callback_data=f"model_{mid}")])
        buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="model_cancel")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        if success:
             await callback.answer(f"Switched to {model_id}!")
             await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=keyboard)
        else:
             await callback.answer(f"Failed to switch to {model_id}.", show_alert=True)

    async def cmd_export(self, message: types.Message):
        """Export the SQLite database."""
        db_path = self.health_service.db.db_path
        if not os.path.exists(db_path):
            await message.answer("❌ Database file not found.")
            return
            
        await message.answer("📦 Exporting database...")
        try:
            file = types.FSInputFile(db_path, filename="remnaguard_backup.db")
            await message.answer_document(file, caption=f"📦 <b>Database Backup</b>\n📅 {self.health_service.db._get_timestamp()}")
        except Exception as e:
            logging.error(f"Export failed: {e}")
            await message.answer(f"❌ Export failed: {e}")

    async def process_feedback_callback(self, callback: types.CallbackQuery):
        """Handle AI feedback."""
        # data: ai_fb:RATING:node_name
        try:
            _, rating, node_name = callback.data.split(":", 2)
            
            # We need the context and verdict from the message text to learn from it.
            # Message text format: "🧠 AI Analysis: {node_name}\n\n{analysis}"
            full_text = callback.message.text or callback.message.caption or ""
            
            # Extract analysis (verdict/content)
            # Remove the header
            if "\n\n" in full_text:
                verdict = full_text.split("\n\n", 1)[1]
            else:
                verdict = full_text
            
            # Get Context (Recent History Summary)
            # This is expensive to re-fetch, but necessary to save "what was happening" 
            # so we can show it as a negative example later.
            history = self.health_service.get_node_history(node_name)
            if history:
                 context_summary = self.health_service.ai._summarize_history(list(history.samples)[-20:]) # Short context
            else:
                 context_summary = "No context available"
            
            # Save to DB
            self.health_service.db.save_feedback(node_name, context_summary, verdict, rating)
            
            # Phase 14/15: SMART UNDO (State-Based)
            # If user says "WRONG" and node has an active incident, CLEAR IT.
            undo_msg = ""
            if rating == "WRONG" and node_name in self.health_service.active_incidents:
                # Remove the incident. The next periodic sync will see it as healthy and restore DNS.
                del self.health_service.active_incidents[node_name]
                
                # Also clear DB persistence if any
                # self.health_service.db.resolve_incident(...) # Optional, loop handles it
                
                undo_msg = "\n🛡️ **Smart Undo Triggered**: Incident cleared. DNS will sync shortly."
                logging.info(f"Smart Undo: Cleared incident for {node_name}")

            await callback.answer(f"Thanks! Feedback recorded: {rating}")
            
            # Remove buttons to prevent double voting
            await callback.message.edit_reply_markup(reply_markup=None)
            
            if undo_msg:
                 await self.bot.send_message(callback.message.chat.id, undo_msg, parse_mode="Markdown")
            
        except Exception as e:
            logging.error(f"Feedback callback failed: {e}")
            await callback.answer(f"Thanks! Feedback recorded: {rating}")
            
            # Remove buttons to prevent double voting
            await callback.message.edit_reply_markup(reply_markup=None)

    async def process_approval_callback(self, callback: types.CallbackQuery):
        """Handle user approval/rejection of AI incidents."""
        # ai_app:ACTION:node_name
        try:
            _, action, node_name = callback.data.split(":", 2)
            
            incident = self.health_service.active_incidents.get(node_name)
            if not incident:
                await callback.answer("❌ Incident no longer active (Already resolved?)", show_alert=True)
                await callback.message.edit_reply_markup(reply_markup=None)
                return

            if action == "CONFIRM":
                incident.state = "CONFIRMED"
                # Clear alerted flag to allow the bot to send the "Incident Confirmed" notification
                # if logic.py's trigger_alert would otherwise block it.
                # Actually, trigger_alert debounces by incident object.
                # Let's just update UI.
                await callback.answer(f"✅ Approved: {node_name} dropped from DNS.")
                await callback.message.edit_text(
                    callback.message.text + f"\n\n✅ **Approved by Admin**. DNS Syncing...",
                    reply_markup=None
                )
                logging.info(f"Admin APPROVED ban for {node_name}")
                
            elif action == "REJECT":
                # Resolve incident as False Positive
                incident.state = "RESOLVED"
                incident.status = "Rejected by Admin"
                
                # Save to DB
                self.health_service.db.save_incident(incident.__dict__)
                
                # Remove from active
                if node_name in self.health_service.active_incidents:
                    del self.health_service.active_incidents[node_name]
                
                await callback.answer(f"❌ Rejected: {node_name} remains in DNS.")
                await callback.message.edit_text(
                    callback.message.text + f"\n\n❌ **Rejected by Admin**. Node remains active.",
                    reply_markup=None
                )
                logging.info(f"Admin REJECTED ban for {node_name}")

        except Exception as e:
            logging.error(f"Approval callback failed: {e}")
            await callback.answer("❌ Error processing approval.")

    async def cmd_dns_sync(self, message: types.Message):
        """Force a manual DNS sync cycle."""
        if not self.health_service.cf.enabled:
            await message.answer("⚠️ Cloudflare Service Disabled.")
            return

        wait_msg = await message.answer("🔄 **Manual DNS Sync Started...**\nFetching current node states and reconciling with Cloudflare API.")
        
        try:
            # 1. Fetch fresh nodes
            nodes = await self.health_service.api_client.get_nodes()
            if not nodes:
                 await wait_msg.edit_text("❌ Failed to fetch nodes from Remnawave.")
                 return
                 
            # 2. Trigger sync
            # We don't want to trigger alerts during manual sync, so we pass an empty list
            changes = await self.health_service._sync_dns_state(nodes, [])
            
            if not changes:
                 await wait_msg.edit_text("✅ **Sync Complete**: Everything is already up to date. No changes needed.")
            else:
                 summary = "\n".join([f"• {c}" for c in changes[:5]])
                 if len(changes) > 5: summary += f"\n...and {len(changes)-5} more."
                 await wait_msg.edit_text(f"🚀 **Sync Complete!**\nApplied {len(changes)} changes to Cloudflare:\n\n{summary}")
                 
        except Exception as e:
            logging.error(f"Manual Sync Failed: {e}")
            await wait_msg.edit_text(f"❌ **Sync Failed**: {e}")

    async def cmd_dns_status(self, message: types.Message):
        """Show current DNS Config & Status."""
        if not self.health_service.cf.enabled:
            await message.answer("⚠️ Cloudflare Service Disabled (Missing Token or Config)")
            return
            
        msg = "🌐 <b>DNS Management Status (State-Based)</b>\n\n"
        
        # Show configured domains
        config = self.health_service.cf.config
        domains = config.get("domains", [])
        
        for d in domains:
            msg += f"<b>Domain</b>: {d.get('domain')}\n"
            for z in d.get("zones", []):
                z_name = z.get('name')
                full = f"{z_name}.{d.get('domain')}" if z_name != "@" else d.get('domain')
                ips = z.get('ips', [])
                msg += f"  • <b>{full}</b>: {len(ips)} IPs configured\n"
                
        # Show specific bans (Incidents that are blocking IPs)
        blocked_nodes = [name for name, inc in self.health_service.active_incidents.items() 
                        if inc.state == "CONFIRMED"]
        
        if blocked_nodes:
            msg += "\n🚫 <b>Active Blocks (Excluded from DNS)</b>:\n"
            for n in blocked_nodes:
                msg += f"  • {n} (Throttled/Unhealthy)\n"
        else:
            msg += "\n✅ All nodes are healthy & synced."
            
        await message.answer(msg, parse_mode="HTML")
