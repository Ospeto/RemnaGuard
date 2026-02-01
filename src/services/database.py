import sqlite3
import os
import logging
import json
from typing import List, Dict, Optional
from contextlib import contextmanager

class DatabaseService:
    """SQLite database for persistent storage."""
    
    def __init__(self, db_path: str = None):
        # Default to data directory
        if db_path is None:
            data_dir = os.getenv("DATA_DIR", "/app/data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "remnaguard.db")
        
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Incidents table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    duration TEXT,
                    max_users INTEGER,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Node samples table (for historical data persistence)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS node_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node TEXT NOT NULL,
                    speed REAL,
                    users INTEGER,
                    efficiency REAL,
                    hour INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Index for faster queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_incidents_node ON incidents(node)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_samples_node ON node_samples(node)')
            
            # Node status log (for uptime tracking)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS node_status_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_node ON node_status_log(node)')

            # AI Feedback Table (Phase 11)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_name TEXT,
                    context_summary TEXT,
                    ai_verdict TEXT,
                    user_rating TEXT, -- ACCURATE or WRONG
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Daily stats (for digest reports)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    incidents_count INTEGER DEFAULT 0,
                    alerts_count INTEGER DEFAULT 0,
                    peak_users INTEGER DEFAULT 0,
                    peak_node TEXT,
                    avg_efficiency REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logging.info(f"Database initialized at {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def save_incident(self, incident: Dict):
        """Save a resolved incident to database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO incidents (node, issue_type, duration, max_users, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                incident.get("node", "Unknown"),
                incident.get("issue", "Unknown"),
                incident.get("duration", "0s"),
                incident.get("max_users", 0),
                incident.get("status", "Unknown")
            ))
            conn.commit()
            
    def get_incidents(self, limit: int = 50) -> List[Dict]:
        """Get recent incidents from database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT node, issue_type as issue, duration, max_users, status, created_at
                FROM incidents
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def save_sample(self, node: str, speed: float, users: int, efficiency: float, hour: int):
        """Save a node sample for historical analysis."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO node_samples (node, speed, users, efficiency, hour)
                VALUES (?, ?, ?, ?, ?)
            ''', (node, speed, users, efficiency, hour))
            conn.commit()
    
    def get_hourly_baselines(self, node: str) -> Dict[int, float]:
        """Get average efficiency per hour for a node."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT hour, AVG(efficiency) as avg_eff
                FROM node_samples
                WHERE node = ? AND users > 0
                GROUP BY hour
            ''', (node,))
            
            rows = cursor.fetchall()
            return {row["hour"]: row["avg_eff"] for row in rows}
    
    def cleanup_old_samples(self, days: int = 7):
        """Remove samples older than N days."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM node_samples
                WHERE created_at < datetime('now', '-' || ? || ' days')
            ''', (days,))
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logging.info(f"Cleaned up {deleted} old samples")

    def get_recent_samples(self, node: str, hours: int = 6) -> List[Dict]:
        """Get recent samples for a node (for restoring NodeHistory)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT speed, users, efficiency, created_at
                FROM node_samples
                WHERE node = ? AND created_at > datetime('now', '-' || ? || ' hours')
                ORDER BY created_at ASC
            ''', (node, hours))
            
            rows = cursor.fetchall()
            return [{"speed": row["speed"], "users": row["users"], "eff": row["efficiency"]} for row in rows]
    
    def get_all_tracked_nodes(self) -> List[str]:
        """Get list of all nodes with stored samples."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT node FROM node_samples')
            rows = cursor.fetchall()
            return [row["node"] for row in rows]

    # === UPTIME TRACKING ===
    
    def log_node_status(self, node: str, status: str):
        """Log a node status change (online/offline)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO node_status_log (node, status)
                VALUES (?, ?)
            ''', (node, status))
            conn.commit()
    
    def get_node_uptime(self, node: str, days: int = 7) -> float:
        """Calculate uptime percentage for a node over N days."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all status changes in the period
            cursor.execute('''
                SELECT status, created_at
                FROM node_status_log
                WHERE node = ? AND created_at > datetime('now', '-' || ? || ' days')
                ORDER BY created_at ASC
            ''', (node, days))
            
            rows = cursor.fetchall()
            if not rows:
                return 100.0  # Assume online if no logs
            
            # Calculate time spent online
            import datetime
            total_seconds = days * 24 * 3600
            online_seconds = 0
            last_online_time = None
            
            for row in rows:
                status = row["status"]
                if status == "online" and last_online_time is None:
                    last_online_time = row["created_at"]
                elif status == "offline" and last_online_time is not None:
                    # Calculate duration online
                    try:
                        start = datetime.datetime.fromisoformat(last_online_time)
                        end = datetime.datetime.fromisoformat(row["created_at"])
                        online_seconds += (end - start).total_seconds()
                    except:
                        pass
                    last_online_time = None
            
            # If still online, count till now
            if last_online_time is not None:
                try:
                    start = datetime.datetime.fromisoformat(last_online_time)
                    online_seconds += (datetime.datetime.now() - start).total_seconds()
                except:
                    pass
            
            uptime_pct = (online_seconds / total_seconds) * 100
            return min(100.0, uptime_pct)
    
    def get_all_uptimes(self, days: int = 7) -> Dict[str, float]:
        """Get uptime for all tracked nodes."""
        nodes = self.get_all_tracked_nodes()
        return {node: self.get_node_uptime(node, days) for node in nodes}

    # === DAILY STATS ===
    
    def save_daily_stats(self, date: str, incidents: int, alerts: int, peak_users: int, peak_node: str, avg_eff: float):
        """Save daily digest stats."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO daily_stats (date, incidents_count, alerts_count, peak_users, peak_node, avg_efficiency)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (date, incidents, alerts, peak_users, peak_node, avg_eff))
            conn.commit()
    
    def get_today_stats(self) -> Dict:
        """Get today's running stats from samples."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Incidents today
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM incidents
                WHERE DATE(created_at) = DATE('now')
            ''')
            incidents = cursor.fetchone()["cnt"]
            
            # Peak users today
            cursor.execute('''
                SELECT node, MAX(users) as peak
                FROM node_samples
                WHERE DATE(created_at) = DATE('now')
                GROUP BY node
                ORDER BY peak DESC
                LIMIT 1
            ''')
            peak_row = cursor.fetchone()
            peak_users = peak_row["peak"] if peak_row else 0
            peak_node = peak_row["node"] if peak_row else "N/A"
            
            # Average efficiency today
            cursor.execute('''
                SELECT AVG(efficiency) as avg_eff
                FROM node_samples
                WHERE DATE(created_at) = DATE('now') AND users > 0
            ''')
            avg_eff = cursor.fetchone()["avg_eff"] or 0 
            
            return {
                "incidents": incidents,
                "peak_users": peak_users,
                "peak_node": peak_node,
                "avg_efficiency": round(avg_eff, 2)
            }

    # === AI FEEDBACK ===

    def save_feedback(self, node_name: str, context: str, verdict: str, rating: str):
        """Save user feedback on AI analysis."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO ai_feedback (node_name, context_summary, ai_verdict, user_rating)
                VALUES (?, ?, ?, ?)
            ''', (node_name, context, verdict, rating))
            conn.commit()
            
    def get_negative_examples(self, limit: int = 3) -> List[Dict]:
        """Get recent examples where AI was marked WRONG."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT node_name, context_summary, ai_verdict
                FROM ai_feedback
                WHERE user_rating = 'WRONG'
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
