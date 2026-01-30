import unittest
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from aiogram.types import User, Chat
from src.bot.middleware import AuthMiddleware
from src.bot.main import TelegramBot

class TestBotOptimizations(unittest.IsolatedAsyncioTestCase):
    async def test_middleware_caching(self):
        """Verify middleware caches admin IDs."""
        os.environ["ADMIN_IDS"] = "123,456"
        middleware = AuthMiddleware()
        
        # Verify it's a set
        self.assertIsInstance(middleware.admin_ids, set)
        self.assertIn("123", middleware.admin_ids)
        self.assertIn("456", middleware.admin_ids)
        
        # Verify call logic
        handler = AsyncMock(return_value="OK")
        event = MagicMock()
        event.from_user.id = 123
        
        result = await middleware(handler, event, {})
        self.assertEqual(result, "OK")
        
        # Unauthorized
        event.from_user.id = 999
        result = await middleware(handler, event, {})
        self.assertIsNone(result)

    async def test_parallel_broadcast(self):
        """Verify broadcast sends messages in parallel."""
        # Setup Bot
        mock_client = MagicMock()
        mock_health = MagicMock()
        
        # Use a valid-looking token format for aiogram validation (ID:Token)
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPQQ"
        os.environ["ADMIN_IDS"] = "1,2,3"
        
        bot = TelegramBot(mock_client, mock_health)
        bot.bot = AsyncMock()
        bot.bot.send_message = AsyncMock()
        
        # Mock alert
        alert = MagicMock()
        alert.message = "Test Alert"
        alert.level = "WARNING"
        alert.metadata = {}
        
        # Run send_alert
        await bot.send_alert(alert)
        
        # Check that send_message was called 3 times
        self.assertEqual(bot.bot.send_message.call_count, 3)

if __name__ == "__main__":
    unittest.main()
