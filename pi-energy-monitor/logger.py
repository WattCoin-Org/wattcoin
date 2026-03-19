"""
Local logging for energy readings (SQLite + JSON)
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class EnergyLogger:
    """Local storage for energy readings"""
    
    def __init__(
        self,
        database_path: str = "energy_data.db",
        json_log: bool = True,
        json_log_path: str = "energy_readings.json",
        retention_days: int = 90
    ):
        self.database_path = database_path
        self.json_log = json_log
        self.json_log_path = json_log_path
        self.retention_days = retention_days
        
        # Initialize database
        self._init_database()
        
        # Clean old data on startup
        self._cleanup_old_data()
    
    def _init_database(self):
        """Initialize SQLite database"""
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        # Create readings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                wallet TEXT NOT NULL,
                watts REAL NOT NULL,
                device_type TEXT NOT NULL,
                client_version TEXT,
                signature TEXT,
                api_reported INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index on timestamp
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_timestamp 
            ON readings(timestamp)
        """)
        
        # Create index on wallet
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_wallet 
            ON readings(wallet)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Database initialized: {self.database_path}")
    
    def log_reading(self, report: dict):
        """Log a power reading to local storage"""
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO readings (
                    timestamp, wallet, watts, device_type, 
                    client_version, signature, api_reported
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                report.get("timestamp"),
                report.get("wallet"),
                report.get("watts"),
                report.get("device_type"),
                report.get("client_version"),
                report.get("signature"),
                1  # Assume API reported (will update if fails)
            ))
            
            conn.commit()
            
            # Also log to JSON if enabled
            if self.json_log:
                self._append_json_log(report)
            
            logger.debug(f"Logged reading: {report.get('watts')}W at {report.get('timestamp')}")
            
        except Exception as e:
            logger.error(f"Failed to log reading: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def _append_json_log(self, report: dict):
        """Append reading to JSON log file"""
        
        try:
            # Load existing logs
            readings = []
            if os.path.exists(self.json_log_path):
                with open(self.json_log_path, 'r') as f:
                    try:
                        readings = json.load(f)
                    except json.JSONDecodeError:
                        readings = []
            
            # Append new reading
            readings.append(report)
            
            # Write back
            with open(self.json_log_path, 'w') as f:
                json.dump(readings, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to write JSON log: {e}")
    
    def get_readings(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000
    ) -> list:
        """Retrieve readings from database"""
        
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM readings WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_statistics(self, hours: int = 24) -> dict:
        """Get statistics for recent readings"""
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        # Calculate time range using timezone-aware datetime
        from datetime import timezone
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as count,
                AVG(watts) as avg_watts,
                MIN(watts) as min_watts,
                MAX(watts) as max_watts,
                SUM(watts) / COUNT(*) as avg_watts_alt
            FROM readings
            WHERE timestamp >= ?
        """, (since,))
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "count": row[0] or 0,
            "avg_watts": round(row[1] or 0, 2),
            "min_watts": round(row[2] or 0, 2),
            "max_watts": round(row[3] or 0, 2),
            "period_hours": hours
        }
    
    def _cleanup_old_data(self):
        """Remove old readings based on retention policy"""
        
        if self.retention_days <= 0:
            return
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        # Calculate cutoff date
        cutoff = (datetime.utcnow() - timedelta(days=self.retention_days)).isoformat() + "Z"
        
        # Delete old readings
        cursor.execute("DELETE FROM readings WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old readings")
    
    def export_csv(self, output_path: str, start_time: str = None, end_time: str = None):
        """Export readings to CSV file"""
        
        import csv
        
        readings = self.get_readings(start_time, end_time, limit=100000)
        
        if not readings:
            logger.warning("No readings to export")
            return
        
        with open(output_path, 'w', newline='') as f:
            if readings:
                writer = csv.DictWriter(f, fieldnames=readings[0].keys())
                writer.writeheader()
                writer.writerows(readings)
        
        logger.info(f"Exported {len(readings)} readings to {output_path}")
    
    def get_total_energy(self, start_time: str = None, end_time: str = None) -> float:
        """Calculate total energy consumed in Wh"""
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        query = "SELECT watts FROM readings WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        cursor.execute(query, params)
        watts_values = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not watts_values:
            return 0.0
        
        # Estimate: assume each reading represents poll_interval seconds
        # This is approximate - for accurate energy, you'd need continuous monitoring
        # For now, just sum the watts (which gives W*s if we knew the interval)
        # We'll return average watts * hours in period as approximation
        
        avg_watts = sum(watts_values) / len(watts_values)
        
        # Estimate based on number of readings and poll interval
        # This is a rough approximation
        estimated_hours = len(watts_values) * 60 / 3600  # Assuming 60s interval
        
        return avg_watts * estimated_hours
