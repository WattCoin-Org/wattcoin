"""
WSI Node Service — manages an inference server process for WattNode.
Handles installation, GPU detection, model serving, and contribution reporting.

This runs as part of WattNode — operators toggle "Serve Inference" and this
module handles starting/stopping the inference server that hosts model layers.

Usage (standalone test):
    python node_service.py status     # Check GPU + inference engine availability
    python node_service.py serve      # Start serving model blocks
    python node_service.py stop       # Stop serving

Usage (from WattNode GUI):
    from services.node_service import NodeService
    svc = NodeService(config)
    svc.check_system()      # → system report
    svc.install()           # → pip install inference dependencies
    svc.start_serving()     # → launch inference server
    svc.stop_serving()      # → stop
    svc.get_status()        # → running/stopped/error

Version: 1.0.0
"""

import os
import sys
import json
import time
import shutil
import logging
import subprocess
import threading
import platform
from pathlib import Path

logger = logging.getLogger("wsi-node")

# =============================================================================
# CONFIG
# =============================================================================

DEFAULT_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"
DEFAULT_NUM_BLOCKS = None   # Auto-detect based on GPU memory
DEFAULT_PORT = 31330        # Inference server default P2P port

# Minimum requirements
MIN_GPU_VRAM_GB = 6         # 6GB minimum for small block counts
RECOMMENDED_VRAM_GB = 8     # 8GB+ recommended
MIN_RAM_GB = 12             # System RAM minimum
MIN_DISK_GB = 20            # Disk space for model weights

# Status file (persists across restarts)
STATUS_FILE = os.path.expanduser("~/.wattnode/node_status.json")


class NodeService:
    """
    Manages an inference server process for serving model inference blocks.
    Designed to be controlled by the WattNode GUI or CLI.
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.model = self.config.get("model", DEFAULT_MODEL)
        self.num_blocks = self.config.get("num_blocks", DEFAULT_NUM_BLOCKS)
        self.port = self.config.get("port", DEFAULT_PORT)
        self.gateway_url = self.config.get("gateway_url", "")
        self.wallet = self.config.get("wallet", "")
        self.node_id = self.config.get("node_id", "")

        self._process = None
        self._log_thread = None
        self._running = False
        self._status = "stopped"
        self._error = None
        self._logs = []  # Recent log lines for GUI display
        self._max_logs = 200

        # Callbacks for GUI updates
        self.on_status_change = None   # (status, message)
        self.on_log = None             # (line)
        self.on_error = None           # (error_message)

        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)

    # =========================================================================
    # SYSTEM CHECKS
    # =========================================================================

    def check_system(self):
        """
        Full system requirements check.
        Returns dict with pass/fail for each requirement.
        Used by GUI setup wizard to show compatibility.
        """
        report = {
            "gpu": self._check_gpu(),
            "ram": self._check_ram(),
            "disk": self._check_disk(),
            "python": self._check_python(),
            "engine_installed": self._check_engine_installed(),
            "torch_installed": self._check_torch_installed(),
            "overall": "unknown"
        }

        # Overall assessment
        gpu_ok = report["gpu"].get("compatible", False)
        ram_ok = report["ram"].get("sufficient", False)
        disk_ok = report["disk"].get("sufficient", False)

        if gpu_ok and ram_ok and disk_ok:
            report["overall"] = "ready" if report["engine_installed"] else "needs_install"
        elif not gpu_ok:
            report["overall"] = "no_gpu"
        else:
            report["overall"] = "insufficient_resources"

        return report

    def _check_gpu(self):
        """Detect NVIDIA GPU and VRAM."""
        result = {
            "found": False,
            "name": None,
            "vram_gb": 0,
            "compatible": False,
            "recommended": False,
            "suggested_blocks": 0,
            "error": None
        }

        try:
            # Try nvidia-smi
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                timeout=10, stderr=subprocess.PIPE
            ).decode().strip()

            if output:
                lines = output.strip().split("\n")
                # Take first GPU
                parts = lines[0].split(",")
                gpu_name = parts[0].strip()
                vram_mb = int(parts[1].strip())
                vram_gb = vram_mb / 1024

                result["found"] = True
                result["name"] = gpu_name
                result["vram_gb"] = round(vram_gb, 1)
                result["compatible"] = vram_gb >= MIN_GPU_VRAM_GB
                result["recommended"] = vram_gb >= RECOMMENDED_VRAM_GB

                # Estimate blocks this GPU can serve
                # Llama 8B: 32 blocks, ~250MB per block on GPU
                blocks_possible = int(vram_gb * 1024 / 300)  # ~300MB per block with overhead
                blocks_possible = min(blocks_possible, 32)    # Can't exceed model's total blocks
                result["suggested_blocks"] = max(1, blocks_possible)

                if len(lines) > 1:
                    result["multi_gpu"] = len(lines)

        except FileNotFoundError:
            result["error"] = "nvidia-smi not found. NVIDIA drivers may not be installed."
        except subprocess.TimeoutExpired:
            result["error"] = "GPU detection timed out."
        except Exception as e:
            result["error"] = f"GPU detection failed: {e}"

        return result

    def _check_ram(self):
        """Check system RAM."""
        try:
            if platform.system() == "Windows":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                c_ulonglong = ctypes.c_ulonglong

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", c_ulonglong),
                        ("ullAvailPhys", c_ulonglong),
                        ("ullTotalPageFile", c_ulonglong),
                        ("ullAvailPageFile", c_ulonglong),
                        ("ullTotalVirtual", c_ulonglong),
                        ("ullAvailVirtual", c_ulonglong),
                        ("ullAvailExtendedVirtual", c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                total_gb = stat.ullTotalPhys / (1024 ** 3)
                avail_gb = stat.ullAvailPhys / (1024 ** 3)
            else:
                import resource
                with open("/proc/meminfo") as f:
                    lines = f.readlines()
                total_kb = int([l for l in lines if "MemTotal" in l][0].split()[1])
                avail_kb = int([l for l in lines if "MemAvailable" in l][0].split()[1])
                total_gb = total_kb / (1024 ** 2)
                avail_gb = avail_kb / (1024 ** 2)

            return {
                "total_gb": round(total_gb, 1),
                "available_gb": round(avail_gb, 1),
                "sufficient": total_gb >= MIN_RAM_GB
            }
        except Exception as e:
            return {"total_gb": 0, "available_gb": 0, "sufficient": False, "error": str(e)}

    def _check_disk(self):
        """Check available disk space."""
        try:
            cache_dir = os.path.expanduser("~/.cache")
            total, used, free = shutil.disk_usage(cache_dir)
            free_gb = free / (1024 ** 3)
            return {
                "free_gb": round(free_gb, 1),
                "sufficient": free_gb >= MIN_DISK_GB,
                "cache_dir": os.path.expanduser("~/.cache/huggingface")
            }
        except Exception as e:
            return {"free_gb": 0, "sufficient": False, "error": str(e)}

    def _check_python(self):
        """Check Python version."""
        v = sys.version_info
        return {
            "version": f"{v.major}.{v.minor}.{v.micro}",
            "compatible": v.major == 3 and v.minor >= 9
        }

    def _check_engine_installed(self):
        """Check if inference engine is installed."""
        try:
            import petals  # noqa: distributed inference engine
            return True
        except ImportError:
            return False

    def _check_torch_installed(self):
        """Check if PyTorch is installed with CUDA."""
        try:
            import torch
            return {
                "installed": True,
                "version": torch.__version__,
                "cuda_available": torch.cuda.is_available(),
                "cuda_version": torch.version.cuda if torch.cuda.is_available() else None
            }
        except ImportError:
            return {"installed": False}

    # =========================================================================
    # INSTALLATION
    # =========================================================================

    def install(self, progress_callback=None):
        """
        Install inference engine and dependencies.
        progress_callback(step, total, message) for GUI progress bar.
        """
        steps = [
            ("PyTorch (AI framework)", "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121"),
            ("Transformers (model loading)", "pip install transformers"),
            ("Distributed inference", "pip install petals"),
            ("Accelerate (GPU optimization)", "pip install accelerate"),
        ]

        total = len(steps)
        results = []

        for i, (name, cmd) in enumerate(steps):
            if progress_callback:
                progress_callback(i + 1, total, f"Installing {name}...")

            self._emit_log(f"📦 Installing {name}...")

            try:
                proc = subprocess.run(
                    cmd.split(),
                    capture_output=True, text=True, timeout=600
                )
                success = proc.returncode == 0
                if not success:
                    self._emit_log(f"⚠️ {name}: {proc.stderr[:200]}")
                else:
                    self._emit_log(f"✅ {name} installed")
                results.append({"name": name, "success": success, "error": proc.stderr[:200] if not success else None})
            except subprocess.TimeoutExpired:
                results.append({"name": name, "success": False, "error": "Installation timed out (10min)"})
                self._emit_log(f"❌ {name}: timed out")
            except Exception as e:
                results.append({"name": name, "success": False, "error": str(e)})
                self._emit_log(f"❌ {name}: {e}")

        all_ok = all(r["success"] for r in results)

        if all_ok and progress_callback:
            progress_callback(total, total, "All dependencies installed ✅")

        return {"success": all_ok, "results": results}

    # =========================================================================
    # SERVER MANAGEMENT
    # =========================================================================

    def start_serving(self):
        """
        Start the inference server process.
        This hosts model blocks and joins the P2P swarm.
        """
        if self._running:
            return {"success": False, "error": "Already serving"}

        # Build command
        cmd = [
            sys.executable, "-m", "petals.cli.run_server",  # distributed inference engine
            self.model
        ]

        if self.num_blocks:
            cmd.extend(["--num_blocks", str(self.num_blocks)])

        if self.port:
            cmd.extend(["--port", str(self.port)])

        self._emit_log(f"🚀 Starting inference server...")
        self._emit_log(f"   Model: {self.model}")
        self._emit_log(f"   Blocks: {self.num_blocks or 'auto'}")
        self._emit_log(f"   P2P Port: {self.port}")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            self._running = True
            self._status = "starting"
            self._error = None
            self._save_status()

            if self.on_status_change:
                self.on_status_change("starting", "Inference server launching...")

            # Start log reader thread
            self._log_thread = threading.Thread(target=self._read_logs, daemon=True)
            self._log_thread.start()

            return {"success": True, "pid": self._process.pid}

        except FileNotFoundError:
            err = "Inference engine not installed. Run setup first."
            self._error = err
            self._status = "error"
            self._emit_log(f"❌ {err}")
            return {"success": False, "error": err}
        except Exception as e:
            err = f"Failed to start: {e}"
            self._error = err
            self._status = "error"
            self._emit_log(f"❌ {err}")
            return {"success": False, "error": err}

    def stop_serving(self):
        """Stop the inference server."""
        if not self._running or not self._process:
            self._running = False
            self._status = "stopped"
            return {"success": True, "message": "Not running"}

        self._emit_log("🛑 Stopping inference server...")

        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)

            self._running = False
            self._status = "stopped"
            self._process = None
            self._save_status()

            if self.on_status_change:
                self.on_status_change("stopped", "Inference server stopped")

            self._emit_log("⏹️ Server stopped")
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self):
        """Get current service status."""
        # Check if process is still alive
        if self._process and self._process.poll() is not None:
            # Process exited
            exit_code = self._process.returncode
            self._running = False
            self._status = "crashed" if exit_code != 0 else "stopped"
            self._error = f"Process exited with code {exit_code}" if exit_code != 0 else None

        return {
            "status": self._status,
            "running": self._running,
            "model": self.model,
            "num_blocks": self.num_blocks,
            "port": self.port,
            "pid": self._process.pid if self._process and self._running else None,
            "error": self._error,
            "recent_logs": self._logs[-20:]
        }

    def _read_logs(self):
        """Read inference server output in background thread."""
        try:
            for line in self._process.stdout:
                line = line.rstrip()
                self._emit_log(line)

                # Detect status changes from server output
                lower = line.lower()
                if "ready" in lower and "serving" in lower:
                    self._status = "serving"
                    if self.on_status_change:
                        self.on_status_change("serving", "Node is serving inference blocks ✅")
                elif "loading" in lower or "downloading" in lower:
                    self._status = "loading_model"
                    if self.on_status_change:
                        self.on_status_change("loading_model", line)
                elif "error" in lower or "exception" in lower:
                    self._error = line
                    if self.on_error:
                        self.on_error(line)

        except Exception:
            pass
        finally:
            if self._running:
                self._running = False
                self._status = "stopped"
                self._save_status()

    def _emit_log(self, line):
        """Add log line and notify GUI."""
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {line}"
        self._logs.append(entry)
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]
        if self.on_log:
            self.on_log(entry)
        logger.info(line)

    def _save_status(self):
        """Persist status to disk."""
        try:
            data = {
                "status": self._status,
                "model": self.model,
                "last_updated": datetime.utcnow().isoformat() + "Z"
            }
            with open(STATUS_FILE, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="WSI Node Service")
    parser.add_argument("command", choices=["status", "serve", "stop", "install", "check"],
                        help="Command to run")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model to serve")
    parser.add_argument("--blocks", type=int, default=None, help="Number of blocks to serve")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="P2P port")
    args = parser.parse_args()

    svc = NodeService({
        "model": args.model,
        "num_blocks": args.blocks,
        "port": args.port
    })

    # Wire up console output
    svc.on_log = lambda line: print(line)
    svc.on_status_change = lambda s, m: print(f"\n{'='*40}\n  Status: {s}\n  {m}\n{'='*40}")

    if args.command == "check":
        print("🔍 Checking system requirements...\n")
        report = svc.check_system()
        print(json.dumps(report, indent=2))

    elif args.command == "status":
        status = svc.get_status()
        print(json.dumps(status, indent=2))

    elif args.command == "install":
        print("📦 Installing inference dependencies...\n")
        result = svc.install(progress_callback=lambda s, t, m: print(f"  [{s}/{t}] {m}"))
        print(f"\n{'✅ Done!' if result['success'] else '❌ Some installs failed'}")

    elif args.command == "serve":
        print("🚀 Starting inference server...\n")
        result = svc.start_serving()
        if result["success"]:
            print(f"Server started (PID: {result['pid']})")
            print("Press Ctrl+C to stop\n")
            try:
                while svc._running:
                    time.sleep(1)
            except KeyboardInterrupt:
                svc.stop_serving()
        else:
            print(f"Failed: {result['error']}")

    elif args.command == "stop":
        svc.stop_serving()


if __name__ == "__main__":
    main()
