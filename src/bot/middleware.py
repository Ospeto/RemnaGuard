from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable
import os

class AuthMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.admin_ids = set(os.getenv("ADMIN_IDS", "").split(","))

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Check if user is in admin list
        if str(event.from_user.id) not in self.admin_ids:
            return
            
        return await handler(event, data)
