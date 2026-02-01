import time
import logging
import os
import uuid
from typing import Dict, List, Optional
from collections import defaultdict, deque
from ..services.remnawave import RemnawaveClient
from ..services.database import DatabaseService

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
        self.last_check = 0
        
        # Tracking
        self.active_incidents: Dict[str, Incident] = {}
        self.node_states: Dict[str, Dict] = {} # {node_name: {last_total: int, last_velocity: float}}
        
        # Recent Alerts (for /alerts command)
        self.recent_alerts = deque(maxlen=20)
        
        # Node History (for trend analysis and /graph command)
        self.node_history: Dict[str, NodeHistory] = {}
        
        # Database (for persistent storage)
        self.db = DatabaseService()
        
        # AI Service & Smart Thresholds
        self.ai = AIService()
        self.smart_thresholds: Dict[str, Dict] = {} # {node: {min_efficiency: float, min_speed: float}}
        
        # Restore node history from database
        self._restore_node_history()
        
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
        """Return history of resolved incidents from database."""
        return list(self.active_incidents.values()) # Assuming tracked_incidents refers to active_incidents

    async def update_smart_baselines(self):
        """Batch job: Updates smart thresholds using AI."""
        if not self.ai.enabled:
            return
            
        logging.info("Starting AI Smart Baseline update...")
        try:
            # Collect history for all nodes (last 24h ideally, but we have what we have in memory)
            # For better accuracy we might want to fetch from DB, but memory is faster.
            # NodeHistory in memory keeps 24h max anyway.
            
            all_history = {}
            for name, hist in self.node_history.items():
                # Convert deque to list of dicts
                all_history[name] = list(hist.samples)
            
            if not all_history:
                logging.info("No history to analyze.")
                return

            new_thresholds = await self.ai.get_smart_thresholds(all_history)
            
            if new_thresholds:
                self.smart_thresholds = new_thresholds
                logging.info(f"Updated Smart Thresholds for {len(new_thresholds)} nodes.")
                logging.info(f"Thresholds: {self.smart_thresholds}")
            else:
                logging.warning("AI returned no thresholds.")
                
        except Exception as e:
            logging.error(f"Failed to update smart baselines: {e}")

    def get_node_history(self, node_name: str) -> Optional[NodeHistory]:
        """Return NodeHistory object for a specific node."""
        return self.node_history.get(node_name)
    
    def get_all_node_names(self) -> List[str]:
        """Return list of all tracked node names."""
        return list(self.node_history.keys())
    
    def _restore_node_history(self):
        """Restore node history from database on startup."""
        try:
            tracked_nodes = self.db.get_all_tracked_nodes()
            for node_name in tracked_nodes:
                samples = self.db.get_recent_samples(node_name, hours=6)
                if samples:
                    history = NodeHistory(node_name)
                    for s in samples:
                        history.samples.append({
                            "ts": time.time(),  # Approximate (lost precision, but good enough for trend)
                            "speed": s["speed"],
                            "users": s["users"],
                            "eff": s["eff"]
                        })
                    self.node_history[node_name] = history
                    logging.info(f"Restored {len(samples)} samples for {node_name}")
            
            # Cleanup very old samples on startup (keep 90 days for AI analysis)
            self.db.cleanup_old_samples(days=90)
        except Exception as e:
            logging.warning(f"Could not restore node history: {e}")

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
        
        # 1. Track Online/Offline Status for Uptime
        is_connected = node.get("isConnected", True)
        status = node.get("status", "online")
        is_online = is_connected and str(status).lower() != "offline"
        
        # Track status transitions
        last_status = self.node_states[name].get("last_status", None)
        if last_status is None:
            # First time seeing this node
            self.node_states[name]["last_status"] = is_online
            self.db.log_node_status(name, "online" if is_online else "offline")
        elif last_status != is_online:
            # Status changed
            self.db.log_node_status(name, "online" if is_online else "offline")
            self.node_states[name]["last_status"] = is_online
            
        if not is_online:
            # Node is offline - skip processing but track it
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
        is_startup = False
        
        # STARTUP CHECK: If last_total is 0, this is the first run (or restart).
        # We cannot calculate velocity yet. Just store the new total.
        if last_total == 0:
             state["last_total"] = total_bytes
             is_startup = True
             logging.debug(f"Startup: Initialized baseline for {name}")

        if not is_startup and total_bytes >= last_total:
            diff = total_bytes - last_total
            velocity = ((diff) / elapsed) / 1024.0 # KB/s
            
        # Update State
        if not is_startup:
            state["last_total"] = total_bytes
        # Smooth velocity (decay)
        last_velocity = state.get("last_velocity", 0.0)
        if velocity > 0:
            smoothed_velocity = velocity
        else:
            smoothed_velocity = last_velocity * 0.8 # Decay
            if smoothed_velocity < 1.0: smoothed_velocity = 0.0
        state["last_velocity"] = smoothed_velocity
        
        # 4. Record Sample to History (ALWAYS - even on startup for node discovery)
        efficiency = smoothed_velocity / users if users > 0 else 0.0
        hour = int(time.strftime("%H"))
        
        if name not in self.node_history:
            self.node_history[name] = NodeHistory(name)
        self.node_history[name].add_sample(smoothed_velocity, users, efficiency)
        
        # 5. Persist to database for AI analysis
        try:
            self.db.save_sample(name, smoothed_velocity, users, efficiency, hour)
        except Exception as e:
            logging.warning(f"Failed to save sample: {e}")
        
        # 5. Detection Logic (Skip on startup to avoid false positives)
        if is_startup:
            return
        
        # 5. Detection Logic (The State Machine)
        await self._update_incident_state(name, smoothed_velocity, users, alerts)


    async def _update_incident_state(self, name: str, speed: float, users: int, alerts: List[Alert]):
        """
        State Machine Logic:
        Healthy -> Suspicious (Log) -> Verifying (Wait) -> Confirmed (Alert)
        """
        incident = self.active_incidents.get(name)
        
        # Thresholds (Dynamic Smart Baselines if available)
        limit_users = self.config["min_users"]
        limit_speed = self.config["min_speed"] # Default
        limit_efficiency = self.config["min_efficiency"] # Default
        
        # Override with Smart Thresholds if available
        if name in self.smart_thresholds:
            smart = self.smart_thresholds[name]
            limit_efficiency = smart.get("min_efficiency", limit_efficiency)
            limit_speed = smart.get("min_speed", limit_speed)
            # Log roughly every hour or so? No, too noisy.
            # Just trust it.
        
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
            
            # Rule 3: ANOMALY Detection (Significant deviation from historical baseline)
            # Only if we have enough history for this node
            if name in self.node_history:
                hist = self.node_history[name]
                baseline = hist.get_baseline()
                if baseline > 0 and efficiency > 0:
                    deviation_pct = ((efficiency - baseline) / baseline) * 100
                    # If efficiency is < 50% of baseline, flag as anomaly
                    if deviation_pct < -50 and not is_bad:  # Only if not already flagged
                        is_bad = True
                        issue_type = "ANOMALY"
        
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
                 incident_data = {
                     "node": name,
                     "issue": incident.issue_type,
                     "duration": f"{incident.duration():.0f}s",
                     "max_users": max(l["users"] for l in incident.logs),
                     "status": "Auto-Resolved (Silent)"
                 }
                 # Save to database (persistent)
                 self.db.save_incident(incident_data)
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
                # Direct alert (Smart Thresholds already applied in detection step)
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
