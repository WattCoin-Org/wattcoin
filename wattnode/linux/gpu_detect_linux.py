# SPDX-License-Identifier: MIT

import subprocess
import re
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


def get_nvidia_gpu_info() -> Optional[Dict[str, Any]]:
    """Detect NVIDIA GPU using nvidia-smi command."""
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=name,memory.total,driver_version,gpu_uuid',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logger.debug("nvidia-smi command failed or GPU not found")
            return None

        lines = result.stdout.strip().split('\n')
        if not lines or not lines[0].strip():
            return None

        # Parse first GPU info
        gpu_data = lines[0].strip().split(', ')
        if len(gpu_data) >= 4:
            return {
                'vendor': 'NVIDIA',
                'name': gpu_data[0],
                'memory_mb': int(gpu_data[1]) if gpu_data[1].isdigit() else 0,
                'driver_version': gpu_data[2],
                'uuid': gpu_data[3],
                'count': len(lines)
            }
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        logger.debug("nvidia-smi not available or failed")
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse nvidia-smi output: {e}")

    return None


def get_amd_gpu_info() -> Optional[Dict[str, Any]]:
    """Detect AMD GPU using rocm-smi or lspci fallback."""
    # Try rocm-smi first
    try:
        result = subprocess.run(['rocm-smi', '--showproductname'],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and 'GPU' in result.stdout:
            gpu_match = re.search(r'GPU\[(\d+)\].*:\s*(.+)', result.stdout)
            if gpu_match:
                return {
                    'vendor': 'AMD',
                    'name': gpu_match.group(2).strip(),
                    'memory_mb': 0,  # rocm-smi memory query is complex
                    'driver_version': 'unknown',
                    'uuid': f"amd-gpu-{gpu_match.group(1)}",
                    'count': 1
                }
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback to lspci for AMD detection
    try:
        result = subprocess.run(['lspci', '-nn'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            amd_gpus = re.findall(r'VGA.*AMD.*Radeon.*?(\[.*?\])', result.stdout, re.IGNORECASE)
            if amd_gpus:
                return {
                    'vendor': 'AMD',
                    'name': f"AMD Radeon GPU",
                    'memory_mb': 0,
                    'driver_version': 'unknown',
                    'uuid': 'amd-lspci-detected',
                    'count': len(amd_gpus)
                }
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    return None


def get_intel_gpu_info() -> Optional[Dict[str, Any]]:
    """Detect Intel GPU using lspci."""
    try:
        result = subprocess.run(['lspci', '-nn'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            intel_gpus = re.findall(r'VGA.*Intel.*?(\[.*?\])', result.stdout, re.IGNORECASE)
            if intel_gpus:
                return {
                    'vendor': 'Intel',
                    'name': 'Intel Integrated Graphics',
                    'memory_mb': 0,
                    'driver_version': 'unknown',
                    'uuid': 'intel-lspci-detected',
                    'count': len(intel_gpus)
                }
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    return None


def detect_gpu() -> Dict[str, Any]:
    """
    Detect GPU on Linux system with vendor-specific methods.

    Returns dict with GPU information or empty dict if no GPU found.
    """
    logger.info("Starting GPU detection on Linux...")

    # Try NVIDIA first (most common for compute)
    gpu_info = get_nvidia_gpu_info()
    if gpu_info:
        logger.info(f"Detected NVIDIA GPU: {gpu_info['name']}")
        return gpu_info

    # Try AMD
    gpu_info = get_amd_gpu_info()
    if gpu_info:
        logger.info(f"Detected AMD GPU: {gpu_info['name']}")
        return gpu_info

    # Try Intel as fallback
    gpu_info = get_intel_gpu_info()
    if gpu_info:
        logger.info(f"Detected Intel GPU: {gpu_info['name']}")
        return gpu_info

    logger.warning("No GPU detected on system")
    return {
        'vendor': 'unknown',
        'name': 'No GPU detected',
        'memory_mb': 0,
        'driver_version': 'N/A',
        'uuid': 'no-gpu',
        'count': 0
    }


def get_gpu_memory_usage() -> Optional[Dict[str, int]]:
    """Get current GPU memory usage for NVIDIA GPUs."""
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=memory.used,memory.total',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=5)

        if result.returncode == 0 and result.stdout.strip():
            used_str, total_str = result.stdout.strip().split(', ')
            return {
                'used_mb': int(used_str),
                'total_mb': int(total_str),
                'free_mb': int(total_str) - int(used_str)
            }
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError,
            FileNotFoundError, ValueError) as e:
        logger.debug(f"Could not get GPU memory usage: {e}")

    return None
