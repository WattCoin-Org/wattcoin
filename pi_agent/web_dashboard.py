from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

class WebDashboard:
    def __init__(self, node_manager, db_path='node_data.db'):
        self.node_manager = node_manager
        self.db_path = db_path
        self.init_database()
        self.start_status_updater()

    def init_database(self):
        """Initialize database for storing dashboard data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                task_type TEXT,
                status TEXT,
                created_at TIMESTAMP,
                completed_at TIMESTAMP,
                reward_watt REAL,
                details TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS earnings_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP,
                amount REAL,
                task_id TEXT,
                source TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

    def start_status_updater(self):
        """Start background thread for real-time status updates"""
        def status_updater():
            while True:
                try:
                    status_data = self.get_node_status()
                    socketio.emit('status_update', status_data)
                    time.sleep(5)  # Update every 5 seconds
                except Exception as e:
                    print(f"Status update error: {e}")
                    time.sleep(10)
        
        thread = threading.Thread(target=status_updater, daemon=True)
        thread.start()

    def get_node_status(self):
        """Get current node status"""
        try:
            return {
                'node_id': self.node_manager.node_id,
                'status': self.node_manager.status,
                'uptime': self.node_manager.get_uptime(),
                'cpu_usage': self.node_manager.get_cpu_usage(),
                'memory_usage': self.node_manager.get_memory_usage(),
                'disk_usage': self.node_manager.get_disk_usage(),
                'temperature': self.node_manager.get_temperature(),
                'active_tasks': len(self.node_manager.active_tasks),
                'total_tasks_completed': self.get_total_tasks_completed(),
                'total_watt_earned': self.get_total_watt_earned(),
                'last_ping': self.node_manager.last_ping.isoformat() if self.node_manager.last_ping else None
            }
        except Exception as e:
            return {
                'error': str(e),
                'status': 'error'
            }

    def get_task_history(self, limit=100):
        """Get task execution history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT task_id, task_type, status, created_at, completed_at, reward_watt, details
            FROM task_history
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'task_id': row[0],
                'task_type': row[1],
                'status': row[2],
                'created_at': row[3],
                'completed_at': row[4],
                'reward_watt': row[5],
                'details': json.loads(row[6]) if row[6] else {}
            })
        
        conn.close()
        return tasks

    def get_earnings_summary(self, days=30):
        """Get earnings summary for specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_date = datetime.now() - timedelta(days=days)
        
        cursor.execute('''
            SELECT DATE(timestamp) as date, SUM(amount) as daily_total
            FROM earnings_log
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        ''', (start_date.isoformat(),))
        
        daily_earnings = []
        for row in cursor.fetchall():
            daily_earnings.append({
                'date': row[0],
                'amount': row[1]
            })
        
        cursor.execute('SELECT SUM(amount) FROM earnings_log')
        total_earnings = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(amount) FROM earnings_log WHERE timestamp >= ?', (start_date.isoformat(),))
        period_earnings = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_earnings': total_earnings,
            'period_earnings': period_earnings,
            'daily_breakdown': daily_earnings
        }

    def get_total_tasks_completed(self):
        """Get total number of completed tasks"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM task_history WHERE status = 'completed'")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_total_watt_earned(self):
        """Get total WATT tokens earned"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(amount) FROM earnings_log")
        total = cursor.fetchone()[0]
        conn.close()
        return total or 0

    def log_task_completion(self, task_data):
        """Log completed task to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO task_history 
            (task_id, task_type, status, created_at, completed_at, reward_watt, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_data.get('task_id'),
            task_data.get('task_type'),
            task_data.get('status'),
            task_data.get('created_at'),
            task_data.get('completed_at'),
            task_data.get('reward_watt'),
            json.dumps(task_data.get('details', {}))
        ))
        
        if task_data.get('reward_watt'):
            cursor.execute('''
                INSERT INTO earnings_log (timestamp, amount, task_id, source)
                VALUES (?, ?, ?, ?)
            ''', (
                task_data.get('completed_at'),
                task_data.get('reward_watt'),
                task_data.get('task_id'),
                'task_completion'
            ))
        
        conn.commit()
        conn.close()

# Initialize dashboard instance
dashboard = None

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """API endpoint for node status"""
    if dashboard:
        return jsonify(dashboard.get_node_status())
    return jsonify({'error': 'Dashboard not initialized'})

@app.route('/api/tasks')
def api_tasks():
    """API endpoint for task history"""
    limit = request.args.get('limit', 100, type=int)
    if dashboard:
        return jsonify(dashboard.get_task_history(limit))
    return jsonify([])

@app.route('/api/earnings')
def api_earnings():
    """API endpoint for earnings summary"""
    days = request.args.get('days', 30, type=int)
    if dashboard:
        return jsonify(dashboard.get_earnings_summary(days))
    return jsonify({'total_earnings': 0, 'period_earnings': 0, 'daily_breakdown': []})

@app.route('/api/control/<action>')
def api_control(action):
    """API endpoint for node control"""
    if not dashboard:
        return jsonify({'error': 'Dashboard not initialized'})
    
    try:
        if action == 'start':
            dashboard.node_manager.start()
            return jsonify({'success': True, 'message': 'Node started'})
        elif action == 'stop':
            dashboard.node_manager.stop()
            return jsonify({'success': True, 'message': 'Node stopped'})
        elif action == 'restart':
            dashboard.node_manager.restart()
            return jsonify({'success': True, 'message': 'Node restarted'})
        else:
            return jsonify({'error': 'Unknown action'})
    except Exception as e:
        return jsonify({'error': str(e)})

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    if dashboard:
        emit('status_update', dashboard.get_node_status())

@socketio.on('request_status')
def handle_status_request():
    """Handle status request from client"""
    if dashboard:
        emit('status_update', dashboard.get_node_status())

def create_dashboard_templates():
    """Create HTML templates directory and files"""
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    
    os.makedirs(templates_dir, exist_ok=True)
    os.makedirs(static_dir, exist_ok=True)
    
    # Create basic dashboard template
    dashboard_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Pi Node Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .status-card { background: white; padding: 20px; margin: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
        .metric { text-align: center; padding: 10px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2196F3; }
        .metric-label { color: #666; margin-top: 5px; }
        .task-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .task-table th, .task-table td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
        .status-online { color: #4CAF50; }
        .status-offline { color: #f44336; }
        .controls { margin: 20px 0; }
        .btn { padding: 10px 20px; margin: 5px; border: none; border-radius: 4px; cursor: pointer; }
        .btn-primary { background: #2196F3; color: white; }
        .btn-danger { background: #f44336; color: white; }
        .btn-success { background: #4CAF50; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Pi Node Dashboard</h1>
        
        <div class="controls">
            <button class="btn btn-success" onclick="controlNode('start')">Start Node</button>
            <button class="btn btn-danger" onclick="controlNode('stop')">Stop Node</button>
            <button class="btn btn-primary" onclick="controlNode('restart')">Restart Node</button>
        </div>
        
        <div class="status-grid">
            <div class="status-card">
                <h3>Node Status</h3>
                <div class="metric">
                    <div class="metric-value" id="node-status">Unknown</div>
                    <div class="metric-label">Status</div>
                </div>
            </div>
            
            <div class="status-card">
                <h3>WATT Earnings</h3>
                <div class="metric">
                    <div class="metric-value" id="total-watt">0</div>
                    <div class="metric-label">Total WATT</div>
                </div>
            </div>
            
            <div class="status-card">
                <h3>Tasks Completed</h3>
                <div class="metric">
                    <div class="metric-value" id="total-tasks">0</div>
                    <div class="metric-label">Completed Tasks</div>
                </div>
            </div>
            
            <div class="status-card">
                <h3>System Resources</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <div class="metric">
                        <div class="metric-value" id="cpu-usage">0%</div>
                        <div class="metric-label">CPU</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="memory-usage">0%</div>
                        <div class="metric-label">Memory</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="status-card">
            <h3>Recent Tasks</h3>
            <table class="task-table" id="task-table">
                <thead>
                    <tr>
                        <th>Task ID</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Reward (WATT)</th>
                        <th>Completed</th>
                    </tr>
                </thead>
                <tbody id="task-tbody">
                </tbody>
            </table>
        </div>
        
        <div class="status-card">
            <h3>Earnings Chart</h3>
            <div id="earnings-chart"></div>
        </div>
    </div>

    <script>
        const socket = io();
        
        socket.on('status_update', function(data) {
            updateStatus(data);
        });
        
        function updateStatus(data) {
            document.getElementById('node-status').textContent = data.status || 'Unknown';
            document.getElementById('node-status').className = data.status === 'online' ? 'metric-value status-online' : 'metric-value status-offline';
            document.getElementById('total-watt').textContent = (data.total_watt_earned || 0).toFixed(2);
            document.getElementById('total-tasks').textContent = data.total_tasks_completed || 0;
            document.getElementById('cpu-usage').textContent = (data.cpu_usage || 0).toFixed(1) + '%';
            document.getElementById('memory-usage').textContent = (data.memory_usage || 0).toFixed(1) + '%';
        }
        
        function controlNode(action) {
            fetch(`/api/control/${action}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(data.message);
                    } else {
                        alert('Error: ' + data.error);
                    }
                });
        }
        
        function loadTasks() {
            fetch('/api/tasks?limit=10')
                .then(response => response.json())
                .then(tasks => {
                    const tbody = document.getElementById('task-tbody');
                    tbody.innerHTML = '';
                    tasks.forEach(task => {
                        const row = tbody.insertRow();
                        row.innerHTML = `
                            <td>${task.task_id || 'N/A'}</td>
                            <td>${task.task_type || 'Unknown'}</td>
                            <td>${task.status || 'Unknown'}</td>
                            <td>${(task.reward_watt || 0).toFixed(4)}</td>
                            <td>${task.completed_at ? new Date(task.completed_at).toLocaleString() : 'N/A'}</td>
                        `;
                    });
                });
        }
        
        function loadEarningsChart() {
            fetch('/api/earnings?days=7')
                .then(response => response.json())
                .then(data => {
                    const trace = {
                        x: data.daily_breakdown.map(d => d.date),
                        y: data.daily_breakdown.map(d => d.amount),
                        type: 'scatter',
                        mode: 'lines+markers',
                        name: 'Daily Earnings'
                    };
                    
                    const layout = {
                        title: 'WATT Earnings (Last 7 Days)',
                        xaxis: { title: 'Date' },
                        yaxis: { title: 'WATT Earned' }
                    };
                    
                    Plotly.newPlot('earnings-chart', [trace], layout);
                });
        }
        
        // Initial load
        loadTasks();
        loadEarningsChart();
        
        // Refresh data periodically
        setInterval(loadTasks, 30000);
        setInterval(loadEarningsChart, 300000);
    </script>
</body>
</html>
    '''
    
    with open(os.path.join(templates_dir, 'dashboard.html'), 'w') as f:
        f.write(dashboard_html)

def run_dashboard(node_manager, host='0.0.0.0', port=5000):
    """Run the web dashboard"""
    global dashboard
    dashboard = WebDashboard(node_manager)
    create_dashboard_templates()
    socketio.run(app, host=host, port=port, debug=False)

if __name__ == '__main__':
    # For testing purposes
    class MockNodeManager:
        def __init__(self):
            self.node_id = 'test-node-001'
            self.status = 'online'
            self.active_tasks = []
            self.last_ping = datetime.now()
        
        def get_uptime(self):
            return "2d 5h 30m"
        
        def get_cpu_usage(self):
            return 25.5
        
        def get_memory_usage(self):
            return 60.2
        
        def get_disk_usage(self):
            return 45.8
        
        def get_temperature(self):
            return 42.5
        
        def start(self):
            self.status = 'online'
        
        def stop(self):
            self.status = 'offline'
        
        def restart(self):
            self.status = 'restarting'
    
    mock_node = MockNodeManager()
    run_dashboard(mock_node)