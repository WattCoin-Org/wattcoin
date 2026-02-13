# WattNode GUI Changelog

## v3.0.0 — WSI Inference Tab (February 8, 2026)

### 🧠 WSI Distributed Inference — NEW TAB

**Serve AI Inference** — Earn WATT by hosting AI model layers on the WSI distributed network.

#### Inference Tab Features:
- **System Requirements Check** — One-click scan for GPU, RAM, disk, and inference engine availability
  - Detects NVIDIA GPU model and VRAM
  - Calculates how many model blocks your GPU can serve
  - Shows clear ✅/❌ status for each requirement
- **Setup Wizard** — Automated inference engine dependency installation
  - Installs PyTorch, Transformers, and inference engine (~3GB total)
  - Progress bar with step-by-step status messages
  - Clear labeling of what each package does
  - Retry button on failure
- **Serve Toggle** — Start/stop hosting model layers with one click
  - Launches inference server in background process
  - Live status: Starting → Loading Model → Serving
  - Automatic block allocation based on GPU VRAM
- **Activity Log** — Real-time log of server events
  - Timestamped entries for all operations
  - Shows model download progress, peer connections, queries served
  - Error messages with helpful context

#### Architecture:
- Uses distributed P2P inference engine for decentralized model serving
- Node joins P2P swarm, hosts subset of model transformer blocks
- Queries route through all nodes to produce responses
- Node operators earn WATT proportional to blocks served

#### Requirements:
- NVIDIA GPU with ≥6GB VRAM (8GB+ recommended)
- ≥12GB system RAM
- ≥20GB free disk space (model weights)
- NVIDIA drivers with CUDA support

### Other Changes
- Version bump: v2.0 → v3.0
- Added `services/node_service.py` — Inference server wrapper with GPU detection
- Added `services/inference_gateway.py` — HTTP gateway for API integration
- Added `requirements_inference.txt` — Inference-specific dependencies
- Updated `config.example.yaml` with inference engine configuration section

---

## v2.0.0 — Previous Release

### 🎉 Major Features Added

### **1. Tabbed Interface**
- **Dashboard Tab** - Quick stats, earnings graph, network overview
- **Settings Tab** - Configuration and CPU allocation controls
- **History Tab** - Complete job history with scrollable table

### **2. CPU Allocation Control** 🎛️
- **Slider control** - Choose 25%, 50%, 75%, or 100% CPU usage
- **Real-time display** - Shows "Using X of Y cores"
- **Persistent settings** - Saved to config file
- **Smart allocation** - Prevents system overload

**How it works:**
- Limits concurrent job processing based on allocation
- Lower allocation = fewer simultaneous jobs
- Higher allocation = more throughput, more earnings
- Recommended: 50% for daily use, 75-100% for dedicated nodes

### **3. Real-Time Earnings Graph** 📊
- **Visual earnings tracking** - Line graph shows WATT earned over time
- **Time-series data** - Tracks earnings history with timestamps
- **Automatic updates** - Graph refreshes as jobs complete
- **Professional styling** - Matches WattCoin brand colors

**Powered by matplotlib** - Install with: `pip install matplotlib`

### **4. Enhanced Dashboard**
- **Jobs Completed** counter
- **WATT Earned** total
- **Wallet Balance** (auto-refreshes every 30s)

### **5. Job History Table**
- **Scrollable history** of all completed jobs
- **Job details**: Type, result, WATT earned, timestamp
- **Color-coded status** (green = success, red = failed)
- **Persistent** - History saved to disk

### 🎨 Professional Design
- **Dark theme** matching wattcoin.org
- **Neon green accents** (#39ff14)
- **Clean typography** (Segoe UI / Consolas)
- **Responsive layout** - Resizable window

