import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from src.engine.logic import ClusterHealthService, Alert

class TestAlertLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.get_nodes = AsyncMock() # Correctly mock as async
        self.service = ClusterHealthService(self.mock_client)
        self.service.debug = True # Bypass 10s check
        # Set a clear threshold
        self.service.config["min_efficiency"] = 100

    async def test_no_alert_before_3_hours(self):
        """Verify that no alert is triggered with less than 3 hours of data (360 samples)."""
        # Mock 2 hours of BAD data (240 samples)
        self.service.node_states["TestNode"]["eff_history"] = [10.0] * 240
        self.service.node_states["TestNode"]["last_total"] = 1000
        
        # Mock API response for one more check
        self.mock_client.get_nodes.return_value = [
            {"name": "TestNode", "trafficUsedBytes": 2000, "usersOnline": 10, "isConnected": True, "status": "online"}
        ]
        
        # Force a check
        self.service.last_check = 0 
        alerts = await self.service.check_cluster()
        
        self.assertEqual(len(alerts), 0, "Should not alert with only 2 hours of data")
        self.assertEqual(len(self.service.node_states["TestNode"]["eff_history"]), 241)

    async def test_alert_after_3_hours_bad_efficiency(self):
        """Verify that an alert IS triggered when efficiency is consistently below limit for 3+ hours."""
        # Mock 3 hours of BAD data (360 samples)
        self.service.node_states["TestNode"]["eff_history"] = [10.0] * 360
        self.service.node_states["TestNode"]["last_total"] = 1000
        
        # Mock API response
        self.mock_client.get_nodes.return_value = [
            {"name": "TestNode", "trafficUsedBytes": 1100, "usersOnline": 10, "isConnected": True, "status": "online"}
        ]
        
        # Force a check
        self.service.last_check = 0 
        alerts = await self.service.check_cluster()
        
        self.assertTrue(len(alerts) > 0, "Should trigger alert after 3 hours of bad efficiency")
        self.assertIn("Chronic Congestion", alerts[0].message)

    async def test_recovery_prevents_alert(self):
        """Verify that if the last hour is healthy, NO alert is triggered even if 3h/5h are bad."""
        # 5 hours total: 4 hours BAD, last 1 hour GOOD
        history = ([10.0] * 480) + ([500.0] * 120)
        self.service.node_states["TestNode"]["eff_history"] = history
        self.service.node_states["TestNode"]["last_total"] = 1000
        
        # Current check is GOOD
        self.mock_client.get_nodes.return_value = [
            {"name": "TestNode", "trafficUsedBytes": 20000, "usersOnline": 10, "isConnected": True, "status": "online"}
        ]
        
        self.service.last_check = 0 
        alerts = await self.service.check_cluster()
        
        self.assertEqual(len(alerts), 0, "Should NOT alert if recent 1h is healthy (Recovery Rule)")

if __name__ == "__main__":
    unittest.main()
