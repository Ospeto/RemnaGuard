import psutil
import socket
from typing import Dict, Any

class SystemMonitor:
    def __init__(self):
        pass

    def get_system_stats(self) -> Dict[str, Any]:
        cpu_usage = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "hostname": socket.gethostname(),
            "cpu_percent": cpu_usage,
            "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "disk_percent": disk.percent
        }
    async def run_speed_test(self) -> str:
        return "⚠️ Speed test disabled."
