from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import json
import sqlite3
import threading
import time
import os
from .agent import PiAgent
from .models import TaskModel

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

class Dashboard:
    def __init__(self, agent_instance):
        self.agent = agent_instance
        self.db_path = 'pi_agent.db'
        self.stats_cache = {}
        self.cache_ttl = 30  # 30 seconds cache
        self.last_cache_update = 0
        
    def init_db(self):
        """Initialize dashboard database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_stats (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_tasks INTEGER,
                completed_tasks INTEGER,
                failed_tasks INTEGER,
                pending_tasks INTEGER,
                total_watt_earned REAL,
                node_status TEXT,
                cpu_usage REAL,
                memory_usage REAL,
                disk_usage REAL,
                uptime INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def get_system_stats(self):
        """Get system resource usage stats"""
        try:
            import psutil
            
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            boot_time = psutil.boot_time()
            uptime = time.time() - boot_time
            
            return {
                'cpu_usage': cpu_usage,
                'memory_usage': memory.percent,
                'disk_usage': disk.percent,
                'uptime': int(uptime)
            }
        except ImportError:
            return {
                'cpu_usage': 0,
                'memory_usage': 0,
                'disk_usage': 0,
                'uptime': 0
            }
    
    def get_task_stats(self):
        """Get task completion statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get task counts by status
        cursor.execute('''
            SELECT status, COUNT(*) 
            FROM tasks 
            GROUP BY status
        ''')
        task_counts = dict(cursor.fetchall())
        
        # Get total WATT earned
        cursor.execute('''
            SELECT SUM(watt_reward) 
            FROM tasks 
            WHERE status = 'completed'
        ''')
        total_watt = cursor.fetchone()[0] or 0
        
        # Get recent completion rate (last 24h)
        yesterday = datetime.now() - timedelta(days=1)
        cursor.execute('''
            SELECT COUNT(*) 
            FROM tasks 
            WHERE status = 'completed' 
            AND updated_at > ?
        ''', (yesterday,))
        recent_completions = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_tasks': sum(task_counts.values()),
            'completed_tasks': task_counts.get('completed', 0),
            'failed_tasks': task_counts.get('failed', 0),
            'pending_tasks': task_counts.get('pending', 0),
            'running_tasks': task_counts.get('running', 0),
            'total_watt_earned': total_watt,
            'recent_completions': recent_completions
        }
    
    def get_recent_tasks(self, limit=10):
        """Get recent tasks for display"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT task_id, task_type, status, watt_reward, 
                   created_at, updated_at, error_message
            FROM tasks 
            ORDER BY updated_at DESC 
            LIMIT ?
        ''', (limit,))
        
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'task_id': row[0],
                'task_type': row[1],
                'status': row[2],
                'watt_reward': row[3],
                'created_at': row[4],
                'updated_at': row[5],
                'error_message': row[6]
            })
        
        conn.close()
        return tasks
    
    def get_hourly_stats(self, hours=24):
        """Get hourly task completion stats"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_time = datetime.now() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT 
                strftime('%Y-%m-%d %H:00:00', updated_at) as hour,
                COUNT(*) as completed,
                SUM(watt_reward) as watt_earned
            FROM tasks 
            WHERE status = 'completed' 
            AND updated_at > ?
            GROUP BY hour
            ORDER BY hour
        ''', (start_time,))
        
        hourly_data = []
        for row in cursor.fetchall():
            hourly_data.append({
                'hour': row[0],
                'completed': row[1],
                'watt_earned': row[2] or 0
            })
        
        conn.close()
        return hourly_data
    
    def update_stats_cache(self):
        """Update cached statistics"""
        current_time = time.time()
        if current_time - self.last_cache_update < self.cache_ttl:
            return self.stats_cache
            
        try:
            system_stats = self.get_system_stats()
            task_stats = self.get_task_stats()
            
            self.stats_cache = {
                'system': system_stats,
                'tasks': task_stats,
                'node_status': self.agent.status if hasattr(self.agent, 'status') else 'unknown',
                'last_updated': current_time
            }
            
            # Store stats in database
            self.store_stats_snapshot()
            
            self.last_cache_update = current_time
            
        except Exception as e:
            print(f"Error updating stats cache: {e}")
            
        return self.stats_cache
    
    def store_stats_snapshot(self):
        """Store current stats snapshot in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            stats = self.stats_cache
            system = stats.get('system', {})
            tasks = stats.get('tasks', {})
            
            cursor.execute('''
                INSERT INTO dashboard_stats 
                (total_tasks, completed_tasks, failed_tasks, pending_tasks,
                 total_watt_earned, node_status, cpu_usage, memory_usage,
                 disk_usage, uptime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                tasks.get('total_tasks', 0),
                tasks.get('completed_tasks', 0),
                tasks.get('failed_tasks', 0),
                tasks.get('pending_tasks', 0),
                tasks.get('total_watt_earned', 0),
                stats.get('node_status', 'unknown'),
                system.get('cpu_usage', 0),
                system.get('memory_usage', 0),
                system.get('disk_usage', 0),
                system.get('uptime', 0)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error storing stats snapshot: {e}")

# Initialize dashboard instance
dashboard = None

def init_dashboard(agent_instance):
    global dashboard
    dashboard = Dashboard(agent_instance)
    dashboard.init_db()
    return dashboard

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/stats')
def api_stats():
    """API endpoint for current statistics"""
    if dashboard:
        stats = dashboard.update_stats_cache()
        return jsonify(stats)
    return jsonify({'error': 'Dashboard not initialized'})

@app.route('/api/tasks/recent')
def api_recent_tasks():
    """API endpoint for recent tasks"""
    if dashboard:
        limit = request.args.get('limit', 10, type=int)
        tasks = dashboard.get_recent_tasks(limit)
        return jsonify({'tasks': tasks})
    return jsonify({'error': 'Dashboard not initialized'})

@app.route('/api/stats/hourly')
def api_hourly_stats():
    """API endpoint for hourly statistics"""
    if dashboard:
        hours = request.args.get('hours', 24, type=int)
        hourly_data = dashboard.get_hourly_stats(hours)
        return jsonify({'hourly_stats': hourly_data})
    return jsonify({'error': 'Dashboard not initialized'})

@app.route('/api/agent/status')
def api_agent_status():
    """API endpoint for agent status"""
    if dashboard and dashboard.agent:
        status_info = {
            'status': getattr(dashboard.agent, 'status', 'unknown'),
            'node_id': getattr(dashboard.agent, 'node_id', 'unknown'),
            'last_heartbeat': getattr(dashboard.agent, 'last_heartbeat', None),
            'version': getattr(dashboard.agent, 'version', '1.0.0'),
            'uptime': getattr(dashboard.agent, 'start_time', None)
        }
        return jsonify(status_info)
    return jsonify({'error': 'Agent not available'})

@app.route('/api/agent/restart', methods=['POST'])
def api_agent_restart():
    """API endpoint to restart agent"""
    if dashboard and dashboard.agent:
        try:
            # Implement agent restart logic
            result = dashboard.agent.restart()
            return jsonify({'success': True, 'message': 'Agent restarted successfully'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    return jsonify({'error': 'Agent not available'})

@app.route('/api/config')
def api_config():
    """API endpoint for current configuration"""
    if dashboard and dashboard.agent:
        config = getattr(dashboard.agent, 'config', {})
        # Remove sensitive information
        safe_config = {k: v for k, v in config.items() if 'key' not in k.lower() and 'password' not in k.lower()}
        return jsonify(safe_config)
    return jsonify({'error': 'Configuration not available'})

def run_dashboard(agent_instance, host='0.0.0.0', port=8080, debug=False):
    """Run the dashboard web server"""
    init_dashboard(agent_instance)
    app.run(host=host, port=port, debug=debug, threaded=True)

def create_dashboard_thread(agent_instance, host='0.0.0.0', port=8080):
    """Create and start dashboard in separate thread"""
    dashboard_thread = threading.Thread(
        target=run_dashboard,
        args=(agent_instance, host, port),
        daemon=True
    )
    dashboard_thread.start()
    return dashboard_thread