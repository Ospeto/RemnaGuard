import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.engine.logic import ClusterHealthService, Incident

class TestLogicV2(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncMock()
        self.service = ClusterHealthService(self.client)
        # Default config: Users=3, Speed=50, Eff=20
        
    async def test_health_to_suspicious_no_alert(self):
        """Verify that a drop in performance logs a Suspicious event but DOES NOT alert."""
        # Mock API: 10 Users, 100 KB/s (Total) -> 10 KB/s/user (Below limit 20)
        users = 10
        speed = 100 * 1024 # 100 KB/s
        
        node_data = [{
            "name": "Node-1", 
            "trafficUsedBytes": 0, 
            "usersOnline": users,
            "isConnected": True
        }]
        
        # 1. Warmup (Velocity 0)
        self.client.get_nodes.return_value = node_data
        alerts = await self.service.check_cluster()
        self.assertEqual(len(alerts), 0)
        
        # 2. Update with traffic (Elapsed = 10s)
        # We need to simulate time passing for velocity calc
        # check_cluster calculates elapsed internally based on self.last_check
        # We can mock time? Or just hack the node definition.
        # Let's hack the service._process_node logic or just relying on internal state.
        
        # Actually easier: The service calculates velocity from `total_bytes` diff.
        # Let's set initial state manually.
        self.service.node_states["Node-1"]["last_total"] = 1000
        self.service.node_states["Node-1"]["last_velocity"] = 100.0 # already smoothed
        self.service.last_check = 0
        
        # Now run check_cluster with 'bad' stats but NO diff (so velocity decays?)
        # Or just simulate a new reading.
        
        # Let's simulate:
        # Node-1 has 10 users.
        # Calculated Speed is 10 KB/s (Bad, limit is 20).
        # Should Trigger Suspicious.
        
        # We can inject/mock `_update_incident_state` to test pure logic, 
        # or mock `_process_node`.
        # Let's test `_update_incident_state` directly for precision.
        
        alerts = []
        await self.service._update_incident_state("Node-1", speed=100.0, users=10, alerts=alerts)
        
        # Expectation: No Alert, but Incident Created
        self.assertEqual(len(alerts), 0, "Should not alert on first suspicious event")
        self.assertIn("Node-1", self.service.active_incidents)
        self.assertEqual(self.service.active_incidents["Node-1"].state, Incident.STATE_SUSPICIOUS)

    async def test_suspicious_to_resolved(self):
        """Verify that a suspicious event resolves silently if performance improves."""
        # Setup Suspicious Incident
        incident = Incident("Node-1", "LOW_EFFICIENCY", "MEDIUM")
        incident.start_time -= 10 # Started 10s ago
        self.service.active_incidents["Node-1"] = incident
        
        # Receive Good Data: 10 Users, 500 KB/s (50 KB/s/user > 20)
        alerts = []
        # Simulate 2 good logs
        await self.service._update_incident_state("Node-1", speed=500.0, users=10, alerts=alerts)
        await self.service._update_incident_state("Node-1", speed=500.0, users=10, alerts=alerts)
        
        # Expectation: Incident Gone, History Added, No Alert
        self.assertEqual(len(alerts), 0)
        self.assertNotIn("Node-1", self.service.active_incidents)
        self.assertEqual(len(self.service.incident_history), 1)
        self.assertEqual(self.service.incident_history[0]["status"], "Auto-Resolved (Silent)")

    async def test_gfw_signature_fast_track(self):
        """Verify that GFW Signature (High Users, Zero Speed) triggers IMMEDIATE alert."""
        # 10 Users, 0 KB/s
        alerts = []
        await self.service._update_incident_state("Node-GFW", speed=0.0, users=10, alerts=alerts)
        
        # Expectation: Alert Created Immediately
        self.assertEqual(len(alerts), 1)
        self.assertIn("GFW LOCK", alerts[0].message)
        self.assertIn("Node-GFW", self.service.active_incidents)
        self.assertEqual(self.service.active_incidents["Node-GFW"].state, Incident.STATE_CONFIRMED)

if __name__ == "__main__":
    unittest.main()
