import time
import logging
import os
import uuid
from typing import Dict, List, Optional
from collections import defaultdict, deque
from ..services.remnawave import RemnawaveClient

class Alert:
    def __init__(self, level: str, message: str, metadata: Dict = None):
        self.level = level # CRITICAL, WARNING, INFO
        self.message = message
        self.metadata = metadata or {}
        self.timestamp = time.strftime("%H:%M:%S")

    def __str__(self):
        return f"[{self.timestamp}] {self.message}"

class Incident:
    """Tracks a suspicious event through its lifecycle."""
    STATE_SUSPICIOUS = "SUSPICIOUS"
    STATE_VERIFYING = "VERIFYING"
    STATE_CONFIRMED = "CONFIRMED"
    STATE_RESOLVED = "RESOLVED"
    
    def __init__(self, node_name: str, issue_type: str, severity: str):
        self.id = str(uuid.uuid4())[:8]
        self.node_name = node_name
        self.issue_type = issue_type # "THROTTLING", "ZERO_THROUGHPUT", etc
        self.severity = severity     # "HIGH", "MEDIUM", "LOW"
        self.state = self.STATE_SUSPICIOUS
        self.start_time = time.time()
        self.last_update = time.time()
        self.logs = [] # Store samples: (timestamp, speed, users)
        
    def add_log(self, speed: float, users: int):
        self.logs.append({
            "ts": time.time(),
            "speed": speed,
            "users": users
        })
        self.last_update = time.time()
        
    def duration(self) -> float:
        return time.time() - self.start_time

class NodeHistory:
    """Stores historical data for trend and pattern analysis."""
    # 6 hours @ 30s intervals = 720 samples
    MAX_SAMPLES = 720
    
    def __init__(self, name: str):
        self.name = name
        self.samples = deque(maxlen=self.MAX_SAMPLES)
        # Hourly baselines: {hour(0-23): {"sum": float, "count": int}}
        self.hourly_data = defaultdict(lambda: {"sum": 0.0, "count": 0})
        
    def add_sample(self, speed: float, users: int, efficiency: float):
        """Record a new sample."""
        now = time.time()
        hour = int(time.strftime("%H"))
        
        self.samples.append({
            "ts": now,
            "speed": speed,
            "users": users,
            "eff": efficiency
        })
        
        # Update hourly baseline (rolling average for this hour)
        if users > 0:
            self.hourly_data[hour]["sum"] += efficiency
            self.hourly_data[hour]["count"] += 1
    
    def get_trend(self) -> Dict:
        """Calculate trend over last 30 minutes."""
        if len(self.samples) < 60:  # Need at least 30 mins (60 samples @ 30s)
            return {"direction": "UNKNOWN", "change_pct": 0.0}
        
        # Last 10 mins (20 samples)
        recent = list(self.samples)[-20:]
        avg_recent = sum(s["eff"] for s in recent) / len(recent)
        
        # Last 30 mins (60 samples)
        older = list(self.samples)[-60:]
        avg_older = sum(s["eff"] for s in older) / len(older)
        
        if avg_older == 0:
            return {"direction": "UNKNOWN", "change_pct": 0.0}
        
        change_pct = ((avg_recent - avg_older) / avg_older) * 100
        
        if change_pct > 15:
            direction = "UP"
        elif change_pct < -15:
            direction = "DOWN"
        else:
            direction = "STABLE"
            
        return {"direction": direction, "change_pct": round(change_pct, 1)}
    
    def get_baseline(self, hour: int = None) -> float:
        """Get the baseline efficiency for a given hour."""
        if hour is None:
            hour = int(time.strftime("%H"))
        data = self.hourly_data.get(hour, {"sum": 0, "count": 0})
        if data["count"] == 0:
            return 0.0
        return data["sum"] / data["count"]
    
    def get_sparkline(self, hours: int = 6) -> str:
        """Generate ASCII sparkline for the last N hours."""
        # Get samples for the last N hours
        cutoff = time.time() - (hours * 3600)
        relevant = [s for s in self.samples if s["ts"] > cutoff]
        
        if len(relevant) < 10:
            return "⏳ Collecting data..."
        
        # Bucket into ~20 points for display
        bucket_size = max(1, len(relevant) // 20)
        buckets = []
        for i in range(0, len(relevant), bucket_size):
            chunk = relevant[i:i+bucket_size]
            avg_eff = sum(s["eff"] for s in chunk) / len(chunk)
            buckets.append(avg_eff)
        
        if not buckets:
            return "⏳ Collecting data..."
        
        # Normalize to sparkline chars
        chars = "▁▂▃▄▅▆▇█"
        min_val = min(buckets)
        max_val = max(buckets)
        range_val = max_val - min_val if max_val > min_val else 1
        
        sparkline = ""
        for val in buckets:
            idx = int(((val - min_val) / range_val) * (len(chars) - 1))
            sparkline += chars[idx]
        
        return sparkline

class ClusterHealthService:
    def __init__(self, api_client: RemnawaveClient):
        self.api_client = api_client
        self.last_check = time.time()
        
        # Tracking
        # node_states: stores last known traffic data for diff calculation
        self.node_states = defaultdict(lambda: {"last_total": 0, "last_velocity": 0.0})
        
        # Active Incidents: {node_name: Incident}
        self.active_incidents: Dict[str, Incident] = {}
        
        # Closed Incidents Log (for Reporting)
        self.incident_history = deque(maxlen=50)
        
        # Recent Alerts (for /alerts command)
        self.recent_alerts = deque(maxlen=20)
        
        # Node History (for trend analysis and /graph command)
        self.node_history: Dict[str, NodeHistory] = {}
        
        # Load Config
        self.config = {
            "min_users": int(os.getenv("THROTTLE_MIN_USERS", "3")),
            "min_speed": int(os.getenv("THROTTLE_SPEED_LIMIT", "50")),
            "min_efficiency": int(os.getenv("THROTTLE_PER_USER", "20")) # Lower default for V2 to reduce noise
        }
        
        # Tuning Constants
        self.VERIFY_DURATION = 300 # 5 minutes to verify
        self.FAST_TRACK_SPEED = 1.0 # < 1KB/s (virtually zero) with HIGH users is instant alert
        self.FAST_TRACK_USERS = 10 # Need significant load for Fast Track

    def get_config(self) -> Dict:
        return self.config

    def update_config(self, key: str, value: int) -> bool:
        map_key = {
            "users": "min_users",
            "speed": "min_speed",
            "efficiency": "min_efficiency"
        }
        actual_key = map_key.get(key)
        if actual_key:
            self.config[actual_key] = value
            return True
        return False
        
    def get_recent_alerts(self) -> List[str]:
        return [str(a) for a in self.recent_alerts]
        
    def get_incident_history(self) -> List[Dict]:
        """Return history of resolved incidents."""
        return list(self.incident_history)
    
    def get_node_history(self, name: str) -> Optional[NodeHistory]:
        """Return NodeHistory object for a specific node."""
        return self.node_history.get(name)
    
    def get_all_node_names(self) -> List[str]:
        """Return list of all tracked node names."""
        return list(self.node_history.keys())

    async def check_cluster(self) -> List[Alert]:
        alerts = []
        now = time.time()
        elapsed = now - self.last_check
        
        if elapsed < 10 and not getattr(self, 'debug', False):
             return []
             
        try:
            nodes = await self.api_client.get_nodes()
            if not nodes:
                return []
                
            for node in nodes:
                try:
                    await self._process_node(node, elapsed, alerts)
                except Exception as e:
                    logging.error(f"Error processing node {node.get('name')}: {e}")
                    
            self.last_check = now
            return alerts

        except Exception as e:
            logging.error(f"Cluster Health Check Failed: {e}")
            return []

    async def _process_node(self, node: Dict, elapsed: float, alerts: List[Alert]):
        name = node.get("name", "Unknown")
        
        # 1. Skip Offline
        is_connected = node.get("isConnected", True)
        status = node.get("status", "online")
        if not is_connected or str(status).lower() == "offline":
             # If node goes offline while having an incident, maybe close it?
             # For now, let's keep it open until it comes back or timeout.
             return

        # 2. Calculate Metrics
        total_bytes = int(node.get("trafficUsedBytes") or 0)
        if total_bytes == 0:
             up = int(node.get("up", 0))
             down = int(node.get("down", 0))
             total_bytes = up + down
             
        users = int(node.get("usersOnline") or node.get("online_users") or node.get("active_users") or 0)
        
        state = self.node_states[name]
        last_total = state["last_total"]
        
        # Velocity Calc
        velocity = 0.0
        
        # STARTUP CHECK: If last_total is 0, this is the first run (or restart).
        # We cannot calculate velocity yet. Just store the new total and return.
        if last_total == 0:
             state["last_total"] = total_bytes
             logging.debug(f"Startup: Initialized baseline for {name}")
             return

        if total_bytes >= last_total:
            diff = total_bytes - last_total
            velocity = ((diff) / elapsed) / 1024.0 # KB/s
            
        # Update State
        state["last_total"] = total_bytes
        # Smooth velocity (decay)
        last_velocity = state.get("last_velocity", 0.0)
        if velocity > 0:
            smoothed_velocity = velocity
        else:
            smoothed_velocity = last_velocity * 0.8 # Decay
            if smoothed_velocity < 1.0: smoothed_velocity = 0.0
        state["last_velocity"] = smoothed_velocity
        
        # 4. Record Sample to History (for trend analysis)
        efficiency = smoothed_velocity / users if users > 0 else 0.0
        if name not in self.node_history:
            self.node_history[name] = NodeHistory(name)
        self.node_history[name].add_sample(smoothed_velocity, users, efficiency)
        
        # 5. Detection Logic (The State Machine)
        await self._update_incident_state(name, smoothed_velocity, users, alerts)


    async def _update_incident_state(self, name: str, speed: float, users: int, alerts: List[Alert]):
        """
        State Machine Logic:
        Healthy -> Suspicious (Log) -> Verifying (Wait) -> Confirmed (Alert)
        """
        incident = self.active_incidents.get(name)
        
        # Thresholds
        limit_users = self.config["min_users"]
        limit_speed = self.config["min_speed"] # Total bandwidth floor
        limit_efficiency = self.config["min_efficiency"] # Per user
        
        # Detection Rules
        is_bad = False
        issue_type = ""
        
        if users >= limit_users:
            # Rule 1: Efficiency Drop
            efficiency = speed / users
            if efficiency < limit_efficiency:
                is_bad = True
                issue_type = "LOW_EFFICIENCY"
            
            # Rule 2: GFW Signature (HIGH Users, ZERO Speed)
            # This is the "Fast Track" rule - Only triggers with significant load + near-zero traffic
            if users >= self.FAST_TRACK_USERS and speed < self.FAST_TRACK_SPEED:
                is_bad = True
                issue_type = "GHOST_THROTTLE" # GFW signature
        
        # --- STATE TRANSITIONS ---
        
        # Case A: Node is currently Healthy
        if not incident:
            if is_bad:
                # Transition: Healthy -> Suspicious
                new_incident = Incident(name, issue_type, "MEDIUM")
                new_incident.add_log(speed, users)
                self.active_incidents[name] = new_incident
                
                # FAST TRACK?
                if issue_type == "GHOST_THROTTLE":
                    logging.warning(f"FAST TRACK: GFW Signature on {name}")
                    new_incident.state = Incident.STATE_CONFIRMED
                    self._trigger_alert(new_incident, alerts)
                else:
                    logging.info(f"LogicV2: New Suspicious Event {name} ({issue_type})")
            return

        # Case B: Node has Active Incident
        incident.add_log(speed, users)
        
        # B1. Recovery?
        if not is_bad:
            # If healthy again, increment recovery counter or close?
            # Let's verify recovery. If > 1 min healthy? 
            # Simple approach: If healthy for 2 consecutive checks, close.
            # We check last 2 logs.
            recent_logs = incident.logs[-3:]
            # If all recent logs are "good" (implied by execution flow... wait)
            # We need to re-eval goodness of logs or just trust current frame?
            # Let's trust current frame + Previous frame.
            if len(recent_logs) >= 2:
                 # Check if *Incident* is resolved.
                 # Actually, we just check if it stays resolved for a bit.
                 # For simplicity V2: If healthy now, mark Resolved.
                 incident.state = Incident.STATE_RESOLVED
                 self.incident_history.append({
                     "node": name,
                     "issue": incident.issue_type,
                     "duration": f"{incident.duration():.0f}s",
                     "max_users": max(l["users"] for l in incident.logs),
                     "status": "Auto-Resolved (Silent)"
                 })
                 del self.active_incidents[name]
                 logging.info(f"LogicV2: Incident Resolved for {name} (Silent)")
            return

        # B2. Escalation (Verifying -> Confirmed)
        duration = incident.duration()
        
        if incident.state == Incident.STATE_SUSPICIOUS:
            # If it persists for X seconds, move to Verifying
            if duration > 60:
                incident.state = Incident.STATE_VERIFYING
                logging.info(f"LogicV2: Escalating {name} to VERIFYING")
                
        elif incident.state == Incident.STATE_VERIFYING:
            # If it persists for Y seconds, ALERT.
            if duration > self.VERIFY_DURATION:
                incident.state = Incident.STATE_CONFIRMED
                self._trigger_alert(incident, alerts)
                
        # B3. Re-Alert logic for Confirmed?
        # If confirmed, we already alerted. Maybe remind every hour?
        # Handled by dedupe logic in `_trigger_alert` ideally, or just ignored here.

    def _trigger_alert(self, incident: Incident, alerts: List[Alert]):
        # Prevent spam (Once per incident state change usually, but here we might call repeatedly)
        # We checked state change before calling.
        # But for Fast Track, we call immediately.
        
        # We need to debounce alerts for the SAME incident object.
        if getattr(incident, "alerted", False):
            # Maybe re-alert if duration > 1 hour?
            if time.time() - incident.last_update > 3600:
                pass # Re-alert logic could go here
            else:
                return

        incident.alerted = True
        
        msg = f"🐌 {incident.issue_type}: {incident.node_name}"
        if incident.issue_type == "GHOST_THROTTLE":
            msg = f"🚨 GFW LOCK DETECTED: {incident.node_name}"
            
        alert = Alert(
            level="WARNING" if incident.severity == "MEDIUM" else "CRITICAL",
            message=msg,
            metadata={
                "node": incident.node_name,
                "duration": f"{incident.duration():.0f}s",
                "users": str(incident.logs[-1]["users"]),
                "speed": f"{incident.logs[-1]['speed']:.1f} KB/s"
            }
        )
        alerts.append(alert)
        self.recent_alerts.append(alert)
