"""
Local history storage for sensor reports.
"""
import json
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List


class HistoryStore:
    """SQLite-based local history store."""
    
    def __init__(self, db_path: str = "oracle_history.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sensor_type TEXT NOT NULL,
                    reading_value TEXT NOT NULL,
                    unit TEXT,
                    timestamp TEXT NOT NULL,
                    location TEXT,
                    wallet_address TEXT,
                    signature TEXT,
                    api_status TEXT DEFAULT 'pending'
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)
            ''')
            conn.commit()
    
    def store(self, report: Dict):
        """Store a report locally."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO readings 
                    (sensor_type, reading_value, unit, timestamp, location, wallet_address, signature, api_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    report.get('sensor_type'),
                    json.dumps(report.get('reading_value')),
                    report.get('unit'),
                    report.get('timestamp'),
                    report.get('location'),
                    report.get('wallet_address'),
                    report.get('signature'),
                    'sent' if report.get('api_status') == 'success' else 'pending'
                ))
                conn.commit()
    
    def get_recent(self, limit: int = 100) -> List[Dict]:
        """Get recent readings."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM readings ORDER BY timestamp DESC LIMIT ?',
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict:
        """Get statistics about stored readings."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT sensor_type) as sensor_types,
                    MAX(timestamp) as latest,
                    COUNT(CASE WHEN api_status = 'sent' THEN 1 END) as sent_count
                FROM readings
            ''')
            row = cursor.fetchone()
            return {
                "total_readings": row[0],
                "sensor_types": row[1],
                "latest_reading": row[2],
                "sent_to_api": row[3]
            }
