from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import json
import os
import threading
import time
from datetime import datetime
from agent import RaspberryPiAgent
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'raspberry_pi_agent_dashboard'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global agent instance
agent = None
dashboard_data = {
    'status': 'offline',
    'total_watt_earned': 0.0,
    'completed_tasks': [],
    'current_task': None,
    'uptime': 0,
    'last_heartbeat': None,
    'node_id': None,
    'capabilities': [],
    'performance_metrics': {
        'tasks_completed': 0,
        'success_rate': 100.0,
        'avg_completion_time': 0.0,
        'error_count': 0
    }
}

def load_dashboard_data():
    """Load dashboard data from storage"""
    global dashboard_data
    try:
        if os.path.exists('dashboard_data.json'):
            with open('dashboard_data.json', 'r') as f:
                saved_data = json.load(f)
                dashboard_data.update(saved_data)
    except Exception as e:
        logging.error(f"Error loading dashboard data: {e}")

def save_dashboard_data():
    """Save dashboard data to storage"""
    try:
        with open('dashboard_data.json', 'w') as f:
            json.dump(dashboard_data, f, indent=2, default=str)
    except Exception as e:
        logging.error(f"Error saving dashboard data: {e}")

def update_dashboard_from_agent():
    """Update dashboard data from agent status"""
    global agent, dashboard_data
    
    if agent and agent.is_running:
        dashboard_data['status'] = 'online'
        dashboard_data['node_id'] = agent.node_id
        dashboard_data['capabilities'] = agent.capabilities
        dashboard_data['last_heartbeat'] = datetime.now().isoformat()
        
        # Update performance metrics
        if hasattr(agent, 'stats'):
            stats = agent.stats
            dashboard_data['performance_metrics'].update({
                'tasks_completed': stats.get('tasks_completed', 0),
                'success_rate': stats.get('success_rate', 100.0),
                'avg_completion_time': stats.get('avg_completion_time', 0.0),
                'error_count': stats.get('error_count', 0)
            })
            
            dashboard_data['total_watt_earned'] = stats.get('total_watt_earned', 0.0)
    else:
        dashboard_data['status'] = 'offline'
        
    save_dashboard_data()

def background_updater():
    """Background thread to update dashboard data and emit updates"""
    while True:
        try:
            update_dashboard_from_agent()
            socketio.emit('dashboard_update', dashboard_data)
            time.sleep(5)  # Update every 5 seconds
        except Exception as e:
            logging.error(f"Error in background updater: {e}")
            time.sleep(10)

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/status')
def get_status():
    """API endpoint for current status"""
    update_dashboard_from_agent()
    return jsonify(dashboard_data)

@app.route('/api/tasks')
def get_tasks():
    """API endpoint for completed tasks"""
    return jsonify({
        'completed_tasks': dashboard_data['completed_tasks'],
        'current_task': dashboard_data['current_task']
    })

@app.route('/api/start_agent', methods=['POST'])
def start_agent():
    """Start the agent"""
    global agent
    try:
        if not agent:
            agent = RaspberryPiAgent()
        
        if not agent.is_running:
            agent_thread = threading.Thread(target=agent.run)
            agent_thread.daemon = True
            agent_thread.start()
            
        return jsonify({'success': True, 'message': 'Agent started successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stop_agent', methods=['POST'])
def stop_agent():
    """Stop the agent"""
    global agent
    try:
        if agent:
            agent.stop()
        return jsonify({'success': True, 'message': 'Agent stopped successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/restart_agent', methods=['POST'])
def restart_agent():
    """Restart the agent"""
    global agent
    try:
        if agent:
            agent.stop()
            time.sleep(2)
            
        agent = RaspberryPiAgent()
        agent_thread = threading.Thread(target=agent.run)
        agent_thread.daemon = True
        agent_thread.start()
        
        return jsonify({'success': True, 'message': 'Agent restarted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear_tasks', methods=['POST'])
def clear_tasks():
    """Clear completed tasks history"""
    dashboard_data['completed_tasks'] = []
    save_dashboard_data()
    return jsonify({'success': True, 'message': 'Tasks cleared successfully'})

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('dashboard_update', dashboard_data)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    pass

@socketio.on('request_update')
def handle_update_request():
    """Handle manual update request"""
    update_dashboard_from_agent()
    emit('dashboard_update', dashboard_data)

def add_completed_task(task_data):
    """Add a completed task to the dashboard"""
    task_entry = {
        'id': task_data.get('task_id'),
        'type': task_data.get('task_type'),
        'description': task_data.get('description', 'Task completed'),
        'watt_earned': task_data.get('reward', 0.0),
        'completion_time': datetime.now().isoformat(),
        'duration': task_data.get('duration', 0),
        'status': 'completed'
    }
    
    dashboard_data['completed_tasks'].insert(0, task_entry)
    dashboard_data['total_watt_earned'] += task_entry['watt_earned']
    
    # Keep only last 100 tasks
    if len(dashboard_data['completed_tasks']) > 100:
        dashboard_data['completed_tasks'] = dashboard_data['completed_tasks'][:100]
    
    save_dashboard_data()
    socketio.emit('task_completed', task_entry)

def set_current_task(task_data):
    """Set the current active task"""
    dashboard_data['current_task'] = {
        'id': task_data.get('task_id'),
        'type': task_data.get('task_type'),
        'description': task_data.get('description', 'Processing task...'),
        'start_time': datetime.now().isoformat(),
        'status': 'in_progress'
    }
    save_dashboard_data()
    socketio.emit('task_started', dashboard_data['current_task'])

def clear_current_task():
    """Clear the current task"""
    dashboard_data['current_task'] = None
    save_dashboard_data()
    socketio.emit('task_cleared', {})

# Template for the dashboard HTML
dashboard_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Raspberry Pi Agent Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.5/socket.io.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .status { display: flex; gap: 20px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); flex: 1; }
        .metric { text-align: center; }
        .metric-value { font-size: 2em; font-weight: bold; color: #667eea; }
        .metric-label { color: #666; margin-top: 5px; }
        .status-online { color: #4CAF50; }
        .status-offline { color: #f44336; }
        .task-list { max-height: 400px; overflow-y: auto; }
        .task-item { border-bottom: 1px solid #eee; padding: 10px 0; }
        .task-item:last-child { border-bottom: none; }
        .controls { margin-bottom: 20px; }
        .btn { padding: 10px 20px; margin-right: 10px; border: none; border-radius: 5px; cursor: pointer; }
        .btn-primary { background: #667eea; color: white; }
        .btn-success { background: #4CAF50; color: white; }
        .btn-danger { background: #f44336; color: white; }
        .btn-warning { background: #ff9800; color: white; }
        .current-task { background: #e3f2fd; border-left: 4px solid #2196F3; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Raspberry Pi Agent Dashboard</h1>
        <p id="node-info">Node ID: Loading... | Status: <span id="status-indicator">Checking...</span></p>
    </div>

    <div class="controls">
        <button class="btn btn-success" onclick="startAgent()">Start Agent</button>
        <button class="btn btn-danger" onclick="stopAgent()">Stop Agent</button>
        <button class="btn btn-warning" onclick="restartAgent()">Restart Agent</button>
        <button class="btn btn-primary" onclick="clearTasks()">Clear Tasks</button>
    </div>

    <div class="status">
        <div class="card">
            <div class="metric">
                <div class="metric-value" id="watt-earned">0</div>
                <div class="metric-label">WATT Earned</div>
            </div>
        </div>
        <div class="card">
            <div class="metric">
                <div class="metric-value" id="tasks-completed">0</div>
                <div class="metric-label">Tasks Completed</div>
            </div>
        </div>
        <div class="card">
            <div class="metric">
                <div class="metric-value" id="success-rate">100%</div>
                <div class="metric-label">Success Rate</div>
            </div>
        </div>
        <div class="card">
            <div class="metric">
                <div class="metric-value" id="uptime">0m</div>
                <div class="metric-label">Uptime</div>
            </div>
        </div>
    </div>

    <div class="status">
        <div class="card" style="flex: 2;">
            <h3>Current Task</h3>
            <div id="current-task">
                <p>No active task</p>
            </div>
        </div>
        <div class="card">
            <h3>Node Capabilities</h3>
            <div id="capabilities">
                <p>Loading...</p>
            </div>
        </div>
    </div>

    <div class="card">
        <h3>Completed Tasks</h3>
        <div class="task-list" id="task-list">
            <p>No completed tasks</p>
        </div>
    </div>

    <script>
        const socket = io();
        let startTime = new Date();

        socket.on('connect', function() {
            console.log('Connected to dashboard');
        });

        socket.on('dashboard_update', function(data) {
            updateDashboard(data);
        });

        socket.on('task_completed', function(task) {
            addTaskToList(task);
        });

        socket.on('task_started', function(task) {
            updateCurrentTask(task);
        });

        function updateDashboard(data) {
            // Update status
            const statusEl = document.getElementById('status-indicator');
            statusEl.textContent = data.status;
            statusEl.className = data.status === 'online' ? 'status-online' : 'status-offline';

            // Update node info
            document.getElementById('node-info').innerHTML = 
                `Node ID: ${data.node_id || 'Not set'} | Status: <span id="status-indicator" class="${data.status === 'online' ? 'status-online' : 'status-offline'}">${data.status}</span>`;

            // Update metrics
            document.getElementById('watt-earned').textContent = data.total_watt_earned.toFixed(2);
            document.getElementById('tasks-completed').textContent = data.performance_metrics.tasks_completed;
            document.getElementById('success-rate').textContent = data.performance_metrics.success_rate.toFixed(1) + '%';

            // Update uptime
            if (data.status === 'online' && data.last_heartbeat) {
                const now = new Date();
                const uptime = Math.floor((now - startTime) / 60000);
                document.getElementById('uptime').textContent = uptime + 'm';
            }

            // Update capabilities
            const capEl = document.getElementById('capabilities');
            if (data.capabilities && data.capabilities.length > 0) {
                capEl.innerHTML = data.capabilities.map(cap => `<span style="background: #e3f2fd; padding: 5px 10px; border-radius: 15px; margin: 2px; display: inline-block;">${cap}</span>`).join('');
            } else {
                capEl.innerHTML = '<p>No capabilities loaded</p>';
            }

            // Update current task
            updateCurrentTask(data.current_task);

            // Update task list
            updateTaskList(data.completed_tasks);
        }

        function updateCurrentTask(task) {
            const currentTaskEl = document.getElementById('current-task');
            if (task) {
                currentTaskEl.innerHTML = `
                    <div class="current-task" style="padding: 15px; border-radius: 5px;">
                        <strong>${task.type || 'Unknown'}</strong>
                        <p>${task.description}</p>
                        <small>Started: ${new Date(task.start_time).toLocaleString()}</small>
                    </div>
                `;
            } else {
                currentTaskEl.innerHTML = '<p>No active task</p>';
            }
        }

        function updateTaskList(tasks) {
            const taskListEl = document.getElementById('task-list');
            if (tasks && tasks.length > 0) {
                taskListEl.innerHTML = tasks.map(task => `
                    <div class="task-item">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong>${task.type || 'Task'}</strong>
                                <p style="margin: 5px 0; color: #666;">${task.description}</p>
                                <small>${new Date(task.completion_time).toLocaleString()}</small>
                            </div>
                            <div style="text-align: right;">
                                <div style="color: #4CAF50; font-weight: bold;">+${task.watt_earned} WATT</div>
                                <small>${task.duration}s</small>
                            </div>
                        </div>
                    </div>
                `).join('');
            } else {
                taskListEl.innerHTML = '<p>No completed tasks</p>';
            }
        }

        function startAgent() {
            fetch('/api/start_agent', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Agent started successfully');
                    } else {
                        alert('Error starting agent: ' + data.error);
                    }
                });
        }

        function stopAgent() {
            fetch('/api/stop_agent', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Agent stopped successfully');
                    } else {
                        alert('Error stopping agent: ' + data.error);
                    }
                });
        }

        function restartAgent() {
            fetch('/api/restart_agent', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Agent restarted successfully');
                    } else {
                        alert('Error restarting agent: ' + data.error);
                    }
                });
        }

        function clearTasks() {
            if (confirm('Are you sure you want to clear all completed tasks?')) {
                fetch('/api/clear_tasks', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            location.reload();
                        } else {
                            alert('Error clearing tasks');
                        }
                    });
            }
        }

        // Request initial update
        socket.emit('request_update');

        // Auto-refresh every 30 seconds
        setInterval(() => {
            socket.emit('request_update');
        }, 30000);
    </script>
</body>
</html>
'''

# Create templates directory and file
os.makedirs('templates', exist_ok=True)
with open('templates/dashboard.html', 'w') as f:
    f.write(dashboard_template)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Load existing dashboard data
    load_dashboard_data()
    
    # Start background updater thread
    updater_thread = threading.Thread(target=background_updater)
    updater_thread.daemon = True
    updater_thread.start()
    
    print("🚀 Starting Raspberry Pi Agent Dashboard...")
    print("📊 Dashboard will be available at: http://localhost:5000")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)