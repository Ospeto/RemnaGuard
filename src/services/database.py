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
