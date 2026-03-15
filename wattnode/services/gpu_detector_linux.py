#!/usr/bin/env python3
"""
GPU Detection for Linux (NVIDIA)

Uses nvidia-smi to detect GPU capabilities for WSI inference.
"""

import subprocess
import re
from typing import Optional, Dict, Any


def get_nvidia_gpu_info() -> Optional[Dict[str, Any]]:
    """
    Detect NVIDIA GPU using nvidia-smi
    
    Returns:
        Dict with GPU info or None if no NVIDIA GPU found
    """
    try:
        # Run nvidia-smi
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return None
        
        lines = result.stdout.strip().split('\n')
        gpus = []
        
        for line in lines:
            if not line.strip():
                continue
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                gpus.append({
                    'name': parts[0],
                    'vram_gb': int(parts[1]) / 1024,  # Convert MB to GB
                    'driver_version': parts[2],
                    'platform': 'linux'
                })
        
        return gpus[0] if gpus else None
        
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        print(f"GPU detection failed: {e}")
        return None


def calculate_blocks_for_gpu(vram_gb: float) -> int:
    """
    Calculate how many transformer blocks can fit in GPU VRAM
    
    Rule of thumb:
    - Llama 8B: ~0.5GB per block (quantized)
    - 8GB GPU: ~16 blocks
    - 12GB GPU: ~24 blocks
    - 24GB GPU: ~32 blocks (full model)
    """
    if vram_gb < 6:
        return 0  # Not enough VRAM
    elif vram_gb < 8:
        return int(vram_gb * 2)  # ~2 blocks per GB
    elif vram_gb < 12:
        return int(vram_gb * 2.5)
    elif vram_gb < 16:
        return int(vram_gb * 2.8)
    else:
        return 32  # Max for Llama 8B


def check_linux_requirements() -> Dict[str, bool]:
    """
    Check if system meets WSI inference requirements on Linux
    
    Returns:
        Dict of requirement checks
    """
    checks = {
        'nvidia_driver': False,
        'nvidia_smi': False,
        'cuda_available': False,
        'sufficient_vram': False,
        'python3': False,
    }
    
    # Check nvidia-smi
    try:
        subprocess.run(["nvidia-smi", "--version"], 
                      capture_output=True, timeout=5)
        checks['nvidia_smi'] = True
        checks['nvidia_driver'] = True
    except:
        pass
    
    # Check CUDA
    try:
        subprocess.run(["nvcc", "--version"], 
                      capture_output=True, timeout=5)
        checks['cuda_available'] = True
    except:
        pass
    
    # Check VRAM
    gpu_info = get_nvidia_gpu_info()
    if gpu_info and gpu_info.get('vram_gb', 0) >= 6:
        checks['sufficient_vram'] = True
    
    # Check Python
    checks['python3'] = True  # We're running, so Python exists
    
    return checks


if __name__ == "__main__":
    print("🔍 Linux GPU Detection")
    print("=" * 50)
    
    gpu = get_nvidia_gpu_info()
    if gpu:
        print(f"✓ NVIDIA GPU Found: {gpu['name']}")
        print(f"  VRAM: {gpu['vram_gb']:.1f} GB")
        print(f"  Driver: {gpu['driver_version']}")
        print(f"  Recommended blocks: {calculate_blocks_for_gpu(gpu['vram_gb'])}")
    else:
        print("✗ No NVIDIA GPU detected")
    
    print()
    print("Requirements Check:")
    checks = check_linux_requirements()
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")
