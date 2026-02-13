#!/usr/bin/env python3
"""
WattNode GUI v3.0 - Enhanced Windows Desktop Application
Earn WATT by running a light node + serving AI inference

FEATURES:
- Tabbed interface (Dashboard, Inference, Settings, History)
- CPU allocation slider
- WSI Inference tab: GPU detection, dependency install, serve toggle
- Real-time earnings graph
- Job history table
- Wallet balance display
- Performance metrics

Color Palette (matching wattcoin.org):
- Background: #0f0f0f (near black)
- Surface: #1a1a1a (dark gray)
- Border: #2a2a2a (medium gray)
- Text: #ffffff (white)
- Text muted: #888888 (gray)
- Accent: #39ff14 (neon green)
- Accent hover: #32e512
- Error: #ff4444
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import os
import sys
import time
import requests
import multiprocessing
from datetime import datetime, timedelta
from collections import deque

# Try to import node service
try:
    from services.node_service import NodeService
    HAS_NODE_SERVICE = True
except ImportError:
    HAS_NODE_SERVICE = False

# Try to import matplotlib for graphs
try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# === COLORS ===
BG_DARK = "#0f0f0f"
BG_SURFACE = "#1a1a1a"
BG_BORDER = "#2a2a2a"
TEXT_WHITE = "#ffffff"
TEXT_MUTED = "#888888"
ACCENT_GREEN = "#39ff14"
ACCENT_HOVER = "#32e512"
ERROR_RED = "#ff4444"
ACCENT_PURPLE = "#9b59b6"  # WSI / Inference accent

# === CONFIG ===
API_BASE = os.environ.get("WATTCOIN_API_URL", "")
CONFIG_FILE = "wattnode_config.json"
HISTORY_FILE = "wattnode_history.json"
HEARTBEAT_INTERVAL = 60
POLL_INTERVAL = 5
MAX_HISTORY = 100  # Keep last 100 jobs

class WattNodeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("WattNode v3.0")
        self.root.geometry("700x650")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(True, True)
        self.root.minsize(700, 650)
        
        # Try to set icon
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(__file__)
            icon_path = os.path.join(base_path, 'assets', 'icon.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass
        
        # State
        self.running = False
        self.node_id = None
        self.wallet = ""
        self.node_name = ""
        self.jobs_completed = 0
        self.total_earned = 0
        self.wallet_balance = 0
        self.daemon_thread = None
        
        # Settings
        self.cpu_allocation = 50  # Percentage
        self.max_cores = multiprocessing.cpu_count()
        self.allocated_cores = max(1, int(self.max_cores * self.cpu_allocation / 100))
        
        # Inference / Node Service
        self.node_service = None
        self.inference_enabled = False
        self.inference_status = "not_checked"  # not_checked, no_gpu, needs_install, ready, serving, error
        self.gpu_info = None
        
        # History tracking
        self.job_history = deque(maxlen=MAX_HISTORY)
        self.earnings_history = deque(maxlen=100)  # Time-series data for graph
        
        # Load saved data
        self.load_config()
        self.load_history()
        
        # Sync stats from backend
        self.sync_stats_from_backend()
        self.fetch_wallet_balance()
        
        # Build UI
        self.create_widgets()
        
        # Start background stats updater
        self.start_stats_updater()
        
    def load_config(self):
        """Load saved configuration"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.wallet = config.get('wallet', '')
                    self.node_name = config.get('name', '')
                    self.node_id = config.get('node_id')
                    self.cpu_allocation = config.get('cpu_allocation', 50)
            except:
                pass
    
    def load_history(self):
        """Load job history from disk"""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    data = json.load(f)
                    self.job_history = deque(data.get('jobs', []), maxlen=MAX_HISTORY)
                    self.earnings_history = deque(data.get('earnings', []), maxlen=100)
            except:
                pass
    
    def save_config(self):
        """Save configuration"""
        config = {
            'wallet': self.wallet,
            'name': self.node_name,
            'node_id': self.node_id,
            'cpu_allocation': self.cpu_allocation
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    
    def save_history(self):
        """Save job history to disk"""
        data = {
            'jobs': list(self.job_history),
            'earnings': list(self.earnings_history)
        }
        with open(HISTORY_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def sync_stats_from_backend(self):
        """Fetch actual stats from backend on startup"""
        if not self.node_id:
            return
        try:
            resp = requests.get(f"{API_BASE}/api/v1/nodes/{self.node_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    self.jobs_completed = data.get("jobs_completed", 0)
                    self.total_earned = data.get("total_earned", 0)
        except:
            pass
    
    def fetch_wallet_balance(self):
        """Fetch WATT balance for wallet"""
        if not self.wallet:
            return
        try:
            # This would call a Solana RPC or WattCoin API endpoint
            # For now, placeholder
            # resp = requests.get(f"{API_BASE}/api/v1/balance/{self.wallet}", timeout=10)
            # self.wallet_balance = resp.json().get('balance', 0)
            self.wallet_balance = 0  # Placeholder
        except:
            pass
    
    def create_widgets(self):
        """Build the UI with tabs"""
        # Main container
        main = tk.Frame(self.root, bg=BG_DARK, padx=15, pady=10)
        main.pack(fill=tk.BOTH, expand=True)
        
        # === HEADER ===
        header = tk.Frame(main, bg=BG_DARK)
        header.pack(fill=tk.X, pady=(0, 10))
        
        # Logo
        logo_frame = tk.Frame(header, bg=BG_DARK)
        logo_frame.pack(side=tk.LEFT)
        
        tk.Label(logo_frame, text="⚡", font=("Segoe UI", 20), 
                fg=ACCENT_GREEN, bg=BG_DARK).pack(side=tk.LEFT, padx=(0, 8))
        
        title_frame = tk.Frame(logo_frame, bg=BG_DARK)
        title_frame.pack(side=tk.LEFT)
        tk.Label(title_frame, text="WattNode v2.0", font=("Segoe UI", 16, "bold"),
                fg=TEXT_WHITE, bg=BG_DARK).pack(anchor=tk.W)
        tk.Label(title_frame, text="Earn WATT by running a light node",
                font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_DARK).pack(anchor=tk.W)
        
        # Status indicator (top right)
        self.status_indicator = tk.Label(header, text="● Stopped", 
                                         font=("Segoe UI", 10, "bold"),
                                         fg=TEXT_MUTED, bg=BG_DARK)
        self.status_indicator.pack(side=tk.RIGHT)
        
        # === NOTEBOOK (TABS) ===
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background=BG_DARK, borderwidth=0)
        style.configure('TNotebook.Tab', background=BG_SURFACE, foreground=TEXT_WHITE,
                       padding=[20, 10], font=('Segoe UI', 10))
        style.map('TNotebook.Tab', background=[('selected', BG_BORDER)],
                 foreground=[('selected', ACCENT_GREEN)])
        
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Create tabs
        self.dashboard_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.inference_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.settings_tab = tk.Frame(self.notebook, bg=BG_DARK)
        self.history_tab = tk.Frame(self.notebook, bg=BG_DARK)
        
        self.notebook.add(self.dashboard_tab, text="  Dashboard  ")
        self.notebook.add(self.inference_tab, text="  🧠 Inference  ")
        self.notebook.add(self.settings_tab, text="  Settings  ")
        self.notebook.add(self.history_tab, text="  History  ")
        
        # Build each tab
        self.create_dashboard_tab()
        self.create_inference_tab()
        self.create_settings_tab()
        self.create_history_tab()
        
        # === CONTROL BUTTONS (Bottom) ===
        btn_frame = tk.Frame(main, bg=BG_DARK)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.start_btn = tk.Button(btn_frame, text="▶  Start Node", 
                                   font=("Segoe UI", 11, "bold"),
                                   bg=ACCENT_GREEN, fg=BG_DARK,
                                   activebackground=ACCENT_HOVER,
                                   activeforeground=BG_DARK,
                                   relief=tk.FLAT, cursor="hand2",
                                   command=self.toggle_node)
        self.start_btn.pack(fill=tk.X, ipady=10)
    
    def create_dashboard_tab(self):
        """Dashboard with stats and earnings graph"""
        container = tk.Frame(self.dashboard_tab, bg=BG_DARK, padx=10, pady=10)
        container.pack(fill=tk.BOTH, expand=True)
        
        # === QUICK STATS ===
        stats_frame = tk.Frame(container, bg=BG_DARK)
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Jobs completed
        stat1 = tk.Frame(stats_frame, bg=BG_SURFACE, padx=15, pady=12)
        stat1.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(0, 5))
        self.jobs_label = tk.Label(stat1, text=str(self.jobs_completed), 
                                   font=("Segoe UI", 24, "bold"),
                                   fg=ACCENT_GREEN, bg=BG_SURFACE)
        self.jobs_label.pack()
        tk.Label(stat1, text="Jobs Done", font=("Segoe UI", 9),
                fg=TEXT_MUTED, bg=BG_SURFACE).pack()
        
        # WATT earned
        stat2 = tk.Frame(stats_frame, bg=BG_SURFACE, padx=15, pady=12)
        stat2.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(5, 5))
        self.earned_label = tk.Label(stat2, text=str(self.total_earned), 
                                     font=("Segoe UI", 24, "bold"),
                                     fg=ACCENT_GREEN, bg=BG_SURFACE)
        self.earned_label.pack()
        tk.Label(stat2, text="WATT Earned", font=("Segoe UI", 9),
                fg=TEXT_MUTED, bg=BG_SURFACE).pack()
        
        # Wallet balance
        stat3 = tk.Frame(stats_frame, bg=BG_SURFACE, padx=15, pady=12)
        stat3.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(5, 0))
        self.balance_label = tk.Label(stat3, text=f"{self.wallet_balance:,}", 
                                      font=("Segoe UI", 24, "bold"),
                                      fg=ACCENT_GREEN, bg=BG_SURFACE)
        self.balance_label.pack()
        tk.Label(stat3, text="Balance", font=("Segoe UI", 9),
                fg=TEXT_MUTED, bg=BG_SURFACE).pack()
        
        # === EARNINGS GRAPH ===
        if HAS_MATPLOTLIB:
            graph_frame = tk.Frame(container, bg=BG_SURFACE, padx=10, pady=10)
            graph_frame.pack(fill=tk.BOTH, expand=True)
            
            tk.Label(graph_frame, text="Earnings Over Time", 
                    font=("Segoe UI", 11, "bold"),
                    fg=TEXT_WHITE, bg=BG_SURFACE).pack(anchor=tk.W, pady=(0, 10))
            
            self.create_earnings_graph(graph_frame)
        else:
            # Fallback if matplotlib not available
            tk.Label(container, text="Install matplotlib for earnings graph:\npip install matplotlib",
                    font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_DARK,
                    justify=tk.CENTER).pack(expand=True)
    
    def create_earnings_graph(self, parent):
        """Create matplotlib earnings graph"""
        fig = Figure(figsize=(6, 3), dpi=100, facecolor=BG_SURFACE)
        self.ax = fig.add_subplot(111)
        self.ax.set_facecolor(BG_BORDER)
        self.ax.spines['bottom'].set_color(TEXT_MUTED)
        self.ax.spines['left'].set_color(TEXT_MUTED)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.tick_params(colors=TEXT_MUTED, labelsize=8)
        self.ax.set_xlabel('Time', color=TEXT_MUTED, fontsize=9)
        self.ax.set_ylabel('WATT Earned', color=TEXT_MUTED, fontsize=9)
        
        # Initial empty plot
        if not self.earnings_history:
            self.ax.plot([], [], color=ACCENT_GREEN, linewidth=2)
            self.ax.text(0.5, 0.5, 'No data yet', 
                        transform=self.ax.transAxes,
                        ha='center', va='center', color=TEXT_MUTED, fontsize=12)
        
        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.earnings_canvas = canvas
    
    def update_earnings_graph(self):
        """Update the earnings graph with latest data"""
        if not HAS_MATPLOTLIB or not hasattr(self, 'ax'):
            return
        
        self.ax.clear()
        self.ax.set_facecolor(BG_BORDER)
        self.ax.spines['bottom'].set_color(TEXT_MUTED)
        self.ax.spines['left'].set_color(TEXT_MUTED)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.tick_params(colors=TEXT_MUTED, labelsize=8)
        self.ax.set_xlabel('Time', color=TEXT_MUTED, fontsize=9)
        self.ax.set_ylabel('WATT Earned', color=TEXT_MUTED, fontsize=9)
        
        if self.earnings_history:
            times = [datetime.fromisoformat(e['time']) for e in self.earnings_history]
            earnings = [e['total'] for e in self.earnings_history]
            
            self.ax.plot(times, earnings, color=ACCENT_GREEN, linewidth=2)
            self.ax.fill_between(times, earnings, alpha=0.2, color=ACCENT_GREEN)
            
            # Format x-axis
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            fig = self.ax.get_figure()
            fig.autofmt_xdate()
        
        self.earnings_canvas.draw()
    
    # =========================================================================
    # INFERENCE TAB — WSI Distributed Inference
    # =========================================================================

    def create_inference_tab(self):
        """WSI Inference tab — GPU check, dependency install, serve toggle, live logs."""
        container = tk.Frame(self.inference_tab, bg=BG_DARK, padx=15, pady=15)
        container.pack(fill=tk.BOTH, expand=True)

        # === HEADER ===
        header = tk.Frame(container, bg=BG_SURFACE, padx=15, pady=12)
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(header, text="🧠 WSI — Serve AI Inference", font=("Segoe UI", 13, "bold"),
                fg=ACCENT_PURPLE, bg=BG_SURFACE).pack(anchor=tk.W)
        tk.Label(header, text="Earn WATT by hosting AI model layers on the distributed network",
                font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_SURFACE).pack(anchor=tk.W, pady=(3, 0))

        # === SYSTEM STATUS ===
        status_frame = tk.Frame(container, bg=BG_SURFACE, padx=15, pady=12)
        status_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Label(status_frame, text="System Requirements", font=("Segoe UI", 11, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE).pack(anchor=tk.W, pady=(0, 8))

        # GPU row
        gpu_row = tk.Frame(status_frame, bg=BG_SURFACE)
        gpu_row.pack(fill=tk.X, pady=2)
        tk.Label(gpu_row, text="GPU:", font=("Segoe UI", 10), fg=TEXT_MUTED,
                bg=BG_SURFACE, width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.gpu_status_label = tk.Label(gpu_row, text="Not checked",
                font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_SURFACE, anchor=tk.W)
        self.gpu_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # RAM row
        ram_row = tk.Frame(status_frame, bg=BG_SURFACE)
        ram_row.pack(fill=tk.X, pady=2)
        tk.Label(ram_row, text="RAM:", font=("Segoe UI", 10), fg=TEXT_MUTED,
                bg=BG_SURFACE, width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.ram_status_label = tk.Label(ram_row, text="Not checked",
                font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_SURFACE, anchor=tk.W)
        self.ram_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Disk row
        disk_row = tk.Frame(status_frame, bg=BG_SURFACE)
        disk_row.pack(fill=tk.X, pady=2)
        tk.Label(disk_row, text="Disk:", font=("Segoe UI", 10), fg=TEXT_MUTED,
                bg=BG_SURFACE, width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.disk_status_label = tk.Label(disk_row, text="Not checked",
                font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_SURFACE, anchor=tk.W)
        self.disk_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Engine row
        engine_row = tk.Frame(status_frame, bg=BG_SURFACE)
        engine_row.pack(fill=tk.X, pady=2)
        tk.Label(engine_row, text="Engine:", font=("Segoe UI", 10), fg=TEXT_MUTED,
                bg=BG_SURFACE, width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.engine_status_label = tk.Label(engine_row, text="Not checked",
                font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_SURFACE, anchor=tk.W)
        self.engine_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Check System button
        self.check_btn = tk.Button(status_frame, text="🔍  Check System",
                                    font=("Segoe UI", 10, "bold"),
                                    bg=ACCENT_PURPLE, fg=TEXT_WHITE,
                                    activebackground="#8e44ad",
                                    relief=tk.FLAT, cursor="hand2",
                                    command=self.run_system_check)
        self.check_btn.pack(fill=tk.X, ipady=8, pady=(10, 0))

        # === SETUP / INSTALL ===
        self.install_frame = tk.Frame(container, bg=BG_SURFACE, padx=15, pady=12)
        self.install_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Label(self.install_frame, text="Setup", font=("Segoe UI", 11, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE).pack(anchor=tk.W, pady=(0, 5))

        self.install_info_label = tk.Label(self.install_frame,
                text="Run 'Check System' first to see what's needed.",
                font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_SURFACE, wraplength=600,
                justify=tk.LEFT)
        self.install_info_label.pack(anchor=tk.W, pady=(0, 8))

        # Progress bar (hidden until install starts)
        self.install_progress = ttk.Progressbar(self.install_frame, mode='determinate')
        self.install_progress_label = tk.Label(self.install_frame, text="",
                font=("Segoe UI", 9), fg=ACCENT_GREEN, bg=BG_SURFACE)

        self.install_btn = tk.Button(self.install_frame,
                text="📦  Install AI Dependencies (~3GB)",
                font=("Segoe UI", 10, "bold"),
                bg="#2a2a2a", fg=TEXT_MUTED,
                relief=tk.FLAT, cursor="hand2",
                state=tk.DISABLED,
                command=self.run_install)
        self.install_btn.pack(fill=tk.X, ipady=8)

        # === SERVE CONTROLS ===
        serve_frame = tk.Frame(container, bg=BG_SURFACE, padx=15, pady=12)
        serve_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Label(serve_frame, text="Serve Inference", font=("Segoe UI", 11, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE).pack(anchor=tk.W, pady=(0, 5))

        tk.Label(serve_frame,
                text="When enabled, your GPU hosts AI model layers. You earn WATT for each query served.",
                font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_SURFACE, wraplength=600,
                justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

        # Serve status
        self.serve_status_label = tk.Label(serve_frame, text="⏹ Not serving",
                font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_SURFACE)
        self.serve_status_label.pack(anchor=tk.W, pady=(0, 8))

        self.serve_btn = tk.Button(serve_frame,
                text="🚀  Start Serving Inference",
                font=("Segoe UI", 10, "bold"),
                bg="#2a2a2a", fg=TEXT_MUTED,
                relief=tk.FLAT, cursor="hand2",
                state=tk.DISABLED,
                command=self.toggle_inference)
        self.serve_btn.pack(fill=tk.X, ipady=8)

        # === LIVE LOGS ===
        log_frame = tk.Frame(container, bg=BG_SURFACE, padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(log_frame, text="Activity Log", font=("Segoe UI", 10, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE).pack(anchor=tk.W, pady=(0, 5))

        self.inference_log = tk.Text(log_frame, height=8,
                bg=BG_DARK, fg=TEXT_MUTED,
                font=("Consolas", 9),
                relief=tk.FLAT, wrap=tk.WORD,
                state=tk.DISABLED)
        self.inference_log.pack(fill=tk.BOTH, expand=True)

        # Scrollbar
        scrollbar = tk.Scrollbar(self.inference_log, command=self.inference_log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.inference_log.config(yscrollcommand=scrollbar.set)

    def run_system_check(self):
        """Run GPU/RAM/disk check in background thread."""
        self.check_btn.config(state=tk.DISABLED, text="Checking...")
        self._log_inference("🔍 Checking system requirements...")

        def do_check():
            svc = NodeService() if HAS_NODE_SERVICE else None
            if not svc:
                self.root.after(0, lambda: self._system_check_done({
                    "overall": "error",
                    "gpu": {"error": "NodeService not available"},
                    "ram": {"sufficient": False},
                    "disk": {"sufficient": False},
                    "engine_installed": False,
                    "torch_installed": {"installed": False}
                }))
                return

            report = svc.check_system()
            self.node_service = svc
            self.root.after(0, lambda r=report: self._system_check_done(r))

        threading.Thread(target=do_check, daemon=True).start()

    def _system_check_done(self, report):
        """Update UI with system check results."""
        self.check_btn.config(state=tk.NORMAL, text="🔍  Check System")

        # GPU
        gpu = report.get("gpu", {})
        if gpu.get("found"):
            name = gpu.get("name", "Unknown")
            vram = gpu.get("vram_gb", 0)
            blocks = gpu.get("suggested_blocks", 0)
            color = ACCENT_GREEN if gpu.get("compatible") else ERROR_RED
            text = f"✅ {name} — {vram}GB VRAM — ~{blocks} blocks" if gpu.get("compatible") else f"⚠️ {name} — {vram}GB (need ≥6GB)"
            self.gpu_info = gpu
        else:
            color = ERROR_RED
            text = f"❌ No NVIDIA GPU found" + (f" ({gpu.get('error', '')})" if gpu.get('error') else "")
        self.gpu_status_label.config(text=text, fg=color)

        # RAM
        ram = report.get("ram", {})
        total = ram.get("total_gb", 0)
        color = ACCENT_GREEN if ram.get("sufficient") else ERROR_RED
        text = f"{'✅' if ram.get('sufficient') else '⚠️'} {total}GB total" + (" (need ≥12GB)" if not ram.get("sufficient") else "")
        self.ram_status_label.config(text=text, fg=color)

        # Disk
        disk = report.get("disk", {})
        free = disk.get("free_gb", 0)
        color = ACCENT_GREEN if disk.get("sufficient") else ERROR_RED
        text = f"{'✅' if disk.get('sufficient') else '⚠️'} {free}GB free" + (" (need ≥20GB)" if not disk.get("sufficient") else "")
        self.disk_status_label.config(text=text, fg=color)

        # Engine
        installed = report.get("engine_installed", False)
        color = ACCENT_GREEN if installed else TEXT_MUTED
        text = "✅ Installed" if installed else "Not installed"
        self.engine_status_label.config(text=text, fg=color)

        overall = report.get("overall", "unknown")
        self.inference_status = overall

        if overall == "ready":
            self._log_inference("✅ System ready! You can start serving inference.")
            self.install_info_label.config(text="All dependencies installed. Ready to serve!", fg=ACCENT_GREEN)
            self.install_btn.config(state=tk.DISABLED)
            self.serve_btn.config(state=tk.NORMAL, bg=ACCENT_PURPLE, fg=TEXT_WHITE)
        elif overall == "needs_install":
            self._log_inference("📦 GPU compatible. Install inference dependencies to continue.")
            self.install_info_label.config(
                text="Your GPU is compatible! Install the AI inference libraries to enable serving.\n"
                     "This will download ~3GB of AI frameworks (inference engine + dependencies).\n"
                     "Model weights (~5GB) download separately on first serve.",
                fg=TEXT_WHITE)
            self.install_btn.config(state=tk.NORMAL, bg=ACCENT_PURPLE, fg=TEXT_WHITE)
        elif overall == "no_gpu":
            self._log_inference("❌ No compatible GPU found. Inference requires an NVIDIA GPU with ≥6GB VRAM.")
            self.install_info_label.config(
                text="Inference requires an NVIDIA GPU with ≥6GB VRAM.\n"
                     "Your node can still earn WATT from scraping jobs on the Dashboard tab.",
                fg=TEXT_MUTED)
        else:
            self._log_inference(f"⚠️ System check result: {overall}")

    def run_install(self):
        """Install inference dependencies with progress feedback."""
        if not self.node_service:
            return

        self.install_btn.config(state=tk.DISABLED, text="Installing...")
        self.install_progress.pack(fill=tk.X, pady=(5, 3))
        self.install_progress_label.pack(anchor=tk.W)

        self._log_inference("📦 Installing AI inference dependencies...")
        self._log_inference("   This will install inference engine and dependencies (~3GB total).")
        self._log_inference("   This is a one-time setup. Please be patient...")

        def do_install():
            def progress_cb(step, total, message):
                pct = int(step / total * 100)
                self.root.after(0, lambda: self.install_progress.config(value=pct))
                self.root.after(0, lambda m=message: self.install_progress_label.config(text=m))
                self._log_inference_safe(f"   [{step}/{total}] {message}")

            result = self.node_service.install(progress_callback=progress_cb)

            if result["success"]:
                self.root.after(0, self._install_done_success)
            else:
                failed = [r for r in result["results"] if not r["success"]]
                msgs = "; ".join(f"{r['name']}: {r.get('error', '?')}" for r in failed)
                self.root.after(0, lambda: self._install_done_fail(msgs))

        threading.Thread(target=do_install, daemon=True).start()

    def _install_done_success(self):
        """Install completed successfully."""
        self._log_inference("✅ All dependencies installed successfully!")
        self.install_btn.config(text="✅ Installed", state=tk.DISABLED)
        self.install_progress.config(value=100)
        self.install_progress_label.config(text="Complete!")
        self.engine_status_label.config(text="✅ Installed", fg=ACCENT_GREEN)
        self.serve_btn.config(state=tk.NORMAL, bg=ACCENT_PURPLE, fg=TEXT_WHITE)
        self.inference_status = "ready"
        self.install_info_label.config(text="All dependencies installed. Ready to serve!", fg=ACCENT_GREEN)

    def _install_done_fail(self, error_msg):
        """Install failed."""
        self._log_inference(f"❌ Installation failed: {error_msg}")
        self.install_btn.config(text="📦  Retry Install", state=tk.NORMAL, bg=ACCENT_PURPLE)
        self.install_progress_label.config(text=f"Failed: {error_msg[:80]}")

    def toggle_inference(self):
        """Start or stop serving inference."""
        if not self.node_service:
            # Initialize service with config
            self.node_service = NodeService({
                "wallet": self.wallet,
                "node_id": self.node_id,
                "num_blocks": self.gpu_info.get("suggested_blocks") if self.gpu_info else None
            })

        if self.inference_enabled:
            self.stop_inference()
        else:
            self.start_inference()

    def start_inference(self):
        """Start inference server."""
        if not self.wallet:
            messagebox.showwarning("Wallet Required",
                "Please set your wallet address in the Settings tab before serving inference.")
            return

        self._log_inference("🚀 Starting inference server...")
        self.serve_btn.config(state=tk.DISABLED, text="Starting...")

        # Wire up callbacks
        self.node_service.on_log = lambda line: self._log_inference_safe(f"   {line}")
        self.node_service.on_status_change = lambda s, m: self.root.after(0, lambda: self._inference_status_changed(s, m))
        self.node_service.on_error = lambda e: self.root.after(0, lambda: self._inference_error(e))

        # Configure
        self.node_service.wallet = self.wallet
        self.node_service.node_id = self.node_id
        if self.gpu_info:
            self.node_service.num_blocks = self.gpu_info.get("suggested_blocks")

        def do_start():
            result = self.node_service.start_serving()
            if result.get("success"):
                self.root.after(0, lambda: self._inference_started(result))
            else:
                self.root.after(0, lambda: self._inference_error(result.get("error", "Unknown error")))

        threading.Thread(target=do_start, daemon=True).start()

    def _inference_started(self, result):
        """Server started successfully."""
        self.inference_enabled = True
        self.serve_btn.config(
            text="🛑  Stop Serving",
            state=tk.NORMAL,
            bg=ERROR_RED, fg=TEXT_WHITE
        )
        self.serve_status_label.config(
            text=f"🟢 Starting... (PID: {result.get('pid', '?')})",
            fg=ACCENT_GREEN
        )
        self._log_inference(f"✅ Inference server started (PID: {result.get('pid')})")
        self._log_inference("   Downloading model weights on first run (this may take several minutes)...")
        self._log_inference("   Once ready, your node will serve AI queries and earn WATT automatically.")

    def _inference_status_changed(self, status, message):
        """Inference server reported a status change."""
        if status == "serving":
            self.serve_status_label.config(text="🟢 Serving inference blocks", fg=ACCENT_GREEN)
            self._log_inference(f"🧠 {message}")
        elif status == "loading_model":
            self.serve_status_label.config(text=f"⏳ {message[:60]}", fg=ACCENT_PURPLE)
        elif status == "stopped":
            self.serve_status_label.config(text="⏹ Stopped", fg=TEXT_MUTED)

    def _inference_error(self, error):
        """Handle inference error."""
        self._log_inference(f"❌ Error: {error}")
        self.serve_btn.config(
            text="🚀  Start Serving Inference",
            state=tk.NORMAL,
            bg=ACCENT_PURPLE, fg=TEXT_WHITE
        )
        self.serve_status_label.config(text=f"❌ {error[:60]}", fg=ERROR_RED)
        self.inference_enabled = False

    def stop_inference(self):
        """Stop inference server."""
        self._log_inference("🛑 Stopping inference server...")
        self.serve_btn.config(state=tk.DISABLED)

        def do_stop():
            if self.node_service:
                self.node_service.stop_serving()
            self.root.after(0, self._inference_stopped)

        threading.Thread(target=do_stop, daemon=True).start()

    def _inference_stopped(self):
        """Server stopped."""
        self.inference_enabled = False
        self.serve_btn.config(
            text="🚀  Start Serving Inference",
            state=tk.NORMAL,
            bg=ACCENT_PURPLE, fg=TEXT_WHITE
        )
        self.serve_status_label.config(text="⏹ Not serving", fg=TEXT_MUTED)
        self._log_inference("⏹ Inference server stopped.")

    def _log_inference(self, text):
        """Add line to inference log (must be called from main thread)."""
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}\n"
        self.inference_log.config(state=tk.NORMAL)
        self.inference_log.insert(tk.END, line)
        self.inference_log.see(tk.END)
        self.inference_log.config(state=tk.DISABLED)

    def _log_inference_safe(self, text):
        """Thread-safe version — schedules log on main thread."""
        self.root.after(0, lambda: self._log_inference(text))

    # =========================================================================
    # SETTINGS TAB
    # =========================================================================

    def create_settings_tab(self):
        """Settings with CPU allocation"""
        container = tk.Frame(self.settings_tab, bg=BG_DARK, padx=15, pady=15)
        container.pack(fill=tk.BOTH, expand=True)
        
        # === CONFIGURATION ===
        config_frame = tk.Frame(container, bg=BG_SURFACE, padx=15, pady=15)
        config_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(config_frame, text="Node Configuration", font=("Segoe UI", 12, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE).pack(anchor=tk.W, pady=(0, 15))
        
        # Wallet
        tk.Label(config_frame, text="Wallet Address", font=("Segoe UI", 9),
                fg=TEXT_MUTED, bg=BG_SURFACE).pack(anchor=tk.W)
        self.wallet_entry = tk.Entry(config_frame, font=("Consolas", 9),
                                     bg=BG_BORDER, fg=TEXT_WHITE,
                                     insertbackground=TEXT_WHITE,
                                     relief=tk.FLAT)
        self.wallet_entry.pack(fill=tk.X, pady=(3, 12), ipady=8)
        self.wallet_entry.insert(0, self.wallet)
        
        # Node name
        tk.Label(config_frame, text="Node Name", font=("Segoe UI", 9),
                fg=TEXT_MUTED, bg=BG_SURFACE).pack(anchor=tk.W)
        self.name_entry = tk.Entry(config_frame, font=("Segoe UI", 10),
                                   bg=BG_BORDER, fg=TEXT_WHITE,
                                   insertbackground=TEXT_WHITE,
                                   relief=tk.FLAT)
        self.name_entry.pack(fill=tk.X, pady=(3, 12), ipady=8)
        self.name_entry.insert(0, self.node_name or "my-wattnode")
        
        # Node ID (if registered)
        if self.node_id:
            tk.Label(config_frame, text="Node ID", font=("Segoe UI", 9),
                    fg=TEXT_MUTED, bg=BG_SURFACE).pack(anchor=tk.W)
            tk.Label(config_frame, text=self.node_id, font=("Consolas", 10),
                    fg=ACCENT_GREEN, bg=BG_BORDER, anchor=tk.W,
                    pady=8, padx=10).pack(fill=tk.X, pady=(3, 0))
        
        # === CPU ALLOCATION ===
        cpu_frame = tk.Frame(container, bg=BG_SURFACE, padx=15, pady=15)
        cpu_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(cpu_frame, text="CPU Allocation", font=("Segoe UI", 12, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE).pack(anchor=tk.W, pady=(0, 10))
        
        # Slider
        slider_frame = tk.Frame(cpu_frame, bg=BG_SURFACE)
        slider_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.cpu_slider = tk.Scale(slider_frame, from_=25, to=100, 
                                   orient=tk.HORIZONTAL,
                                   resolution=25,
                                   bg=BG_SURFACE, fg=TEXT_WHITE,
                                   activebackground=ACCENT_GREEN,
                                   troughcolor=BG_BORDER,
                                   highlightthickness=0,
                                   sliderlength=30,
                                   command=self.on_cpu_change)
        self.cpu_slider.set(self.cpu_allocation)
        self.cpu_slider.pack(fill=tk.X)
        
        # CPU info
        self.cpu_info_label = tk.Label(cpu_frame, 
                                       text=f"Using {self.allocated_cores} of {self.max_cores} cores ({self.cpu_allocation}%)",
                                       font=("Segoe UI", 10),
                                       fg=ACCENT_GREEN, bg=BG_SURFACE)
        self.cpu_info_label.pack(pady=(0, 10))
        
        # Save button
        save_btn = tk.Button(cpu_frame, text="Save Settings",
                            font=("Segoe UI", 10, "bold"),
                            bg=ACCENT_GREEN, fg=BG_DARK,
                            activebackground=ACCENT_HOVER,
                            relief=tk.FLAT, cursor="hand2",
                            command=self.save_settings)
        save_btn.pack(fill=tk.X, ipady=10)
    
    def create_history_tab(self):
        """Job history table"""
        container = tk.Frame(self.history_tab, bg=BG_DARK, padx=10, pady=10)
        container.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(container, text="Job History", font=("Segoe UI", 12, "bold"),
                fg=TEXT_WHITE, bg=BG_DARK).pack(anchor=tk.W, pady=(0, 10))
        
        # Scrollable frame
        canvas = tk.Canvas(container, bg=BG_DARK, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.history_frame = tk.Frame(canvas, bg=BG_DARK)
        
        self.history_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.history_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Populate history
        self.refresh_history()
    
    def refresh_history(self):
        """Populate job history table"""
        # Clear existing
        for widget in self.history_frame.winfo_children():
            widget.destroy()
        
        if not self.job_history:
            tk.Label(self.history_frame, text="No jobs completed yet",
                    font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_DARK).pack(pady=20)
            return
        
        # Header
        header = tk.Frame(self.history_frame, bg=BG_SURFACE, padx=10, pady=8)
        header.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(header, text="Time", font=("Segoe UI", 9, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE, width=15, anchor=tk.W).pack(side=tk.LEFT)
        tk.Label(header, text="Type", font=("Segoe UI", 9, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE, width=10, anchor=tk.W).pack(side=tk.LEFT)
        tk.Label(header, text="Earned", font=("Segoe UI", 9, "bold"),
                fg=TEXT_WHITE, bg=BG_SURFACE, width=12, anchor=tk.W).pack(side=tk.LEFT)
        
        # Rows
        for job in reversed(list(self.job_history)):
            row = tk.Frame(self.history_frame, bg=BG_BORDER, padx=10, pady=6)
            row.pack(fill=tk.X, pady=1)
            
            tk.Label(row, text=job.get('time', ''), font=("Segoe UI", 9),
                    fg=TEXT_MUTED, bg=BG_BORDER, width=15, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=job.get('type', ''), font=("Segoe UI", 9),
                    fg=TEXT_WHITE, bg=BG_BORDER, width=10, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=f"{job.get('earned', 0)} WATT", font=("Segoe UI", 9),
                    fg=ACCENT_GREEN, bg=BG_BORDER, width=12, anchor=tk.W).pack(side=tk.LEFT)
    
    def on_cpu_change(self, value):
        """Handle CPU slider change"""
        self.cpu_allocation = int(float(value))
        self.allocated_cores = max(1, int(self.max_cores * self.cpu_allocation / 100))
        self.cpu_info_label.config(
            text=f"Using {self.allocated_cores} of {self.max_cores} cores ({self.cpu_allocation}%)"
        )
    
    def save_settings(self):
        """Save configuration"""
        self.wallet = self.wallet_entry.get().strip()
        self.node_name = self.name_entry.get().strip()
        self.save_config()
        messagebox.showinfo("Settings Saved", "Your settings have been saved successfully!")
    
    def toggle_node(self):
        """Start or stop the node"""
        if not self.running:
            # Validate config
            if not self.wallet or not self.node_name:
                messagebox.showerror("Error", "Please configure wallet and node name in Settings tab")
                return
            
            if not self.node_id:
                messagebox.showwarning("Not Registered", 
                                      "Register your node first:\n"
                                      "1. Stake 10,000 WATT to treasury\n"
                                      "2. Contact support with TX signature")
                return
            
            self.start_node()
        else:
            self.stop_node()
    
    def start_node(self):
        """Start the node daemon"""
        self.running = True
        self.start_btn.config(text="■  Stop Node", bg=ERROR_RED)
        self.status_indicator.config(text="● Running", fg=ACCENT_GREEN)
        
        # Start daemon in background thread
        self.daemon_thread = threading.Thread(target=self.node_daemon, daemon=True)
        self.daemon_thread.start()
    
    def stop_node(self):
        """Stop the node daemon"""
        self.running = False
        self.start_btn.config(text="▶  Start Node", bg=ACCENT_GREEN)
        self.status_indicator.config(text="● Stopped", fg=TEXT_MUTED)
    
    def node_daemon(self):
        """Main daemon loop"""
        last_heartbeat = 0
        
        while self.running:
            # Send heartbeat
            if time.time() - last_heartbeat > HEARTBEAT_INTERVAL:
                self.send_heartbeat()
                last_heartbeat = time.time()
            
            # Poll for jobs
            jobs = self.poll_jobs()
            for job in jobs:
                if not self.running:
                    break
                self.process_job(job)
            
            time.sleep(POLL_INTERVAL)
    
    def send_heartbeat(self):
        """Send heartbeat to server"""
        if not self.node_id:
            return
        try:
            requests.post(f"{API_BASE}/api/v1/nodes/heartbeat", 
                         json={"node_id": self.node_id}, timeout=10)
        except:
            pass
    
    def poll_jobs(self):
        """Poll for available jobs"""
        if not self.node_id:
            return []
        try:
            resp = requests.get(f"{API_BASE}/api/v1/nodes/jobs",
                               params={"node_id": self.node_id}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("jobs", [])
        except:
            pass
        return []
    
    def process_job(self, job):
        """Process a single job"""
        job_id = job.get("id")
        job_type = job.get("type")
        job_payload = job.get("payload", {})
        
        # Claim job
        try:
            resp = requests.post(f"{API_BASE}/api/v1/nodes/jobs/{job_id}/claim",
                                json={"node_id": self.node_id}, timeout=10)
            if resp.status_code != 200:
                return
        except:
            return
        
        # Execute job (simplified - actual implementation in services/)
        result = {"success": False}
        if job_type == "scrape":
            # Placeholder
            result = {"success": True, "content": "Scraped content"}
        elif job_type == "inference":
            # Placeholder
            result = {"success": True, "response": "AI response"}
        
        # Submit result
        try:
            resp = requests.post(f"{API_BASE}/api/v1/nodes/jobs/{job_id}/complete",
                                json={"node_id": self.node_id, "result": result}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    earned = data.get("watt_earned", 0)
                    self.on_job_completed(job_type, earned)
        except:
            pass
    
    def on_job_completed(self, job_type, earned):
        """Handle job completion"""
        self.jobs_completed += 1
        self.total_earned += earned
        
        # Add to history
        job_record = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": job_type,
            "earned": earned
        }
        self.job_history.append(job_record)
        
        # Add to earnings history
        earnings_record = {
            "time": datetime.now().isoformat(),
            "total": self.total_earned
        }
        self.earnings_history.append(earnings_record)
        
        # Save
        self.save_history()
        
        # Update UI (thread-safe)
        self.root.after(0, self.update_ui_stats)
    
    def update_ui_stats(self):
        """Update UI with latest stats"""
        self.jobs_label.config(text=str(self.jobs_completed))
        self.earned_label.config(text=f"{self.total_earned:,}")
        self.refresh_history()
        self.update_earnings_graph()
    
    def start_stats_updater(self):
        """Background thread to update stats periodically"""
        def updater():
            while True:
                time.sleep(30)  # Update every 30 seconds
                self.fetch_wallet_balance()
                self.root.after(0, lambda: self.balance_label.config(text=f"{self.wallet_balance:,}"))
        
        threading.Thread(target=updater, daemon=True).start()

def main():
    root = tk.Tk()
    app = WattNodeGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
