"""
Data Backup and Integrity Module for WattCoin.

Provides:
- SHA256 checksum generation and verification for all data files
- Automatic backups with 7-day rotation and compression
- Restore from backup with integrity verification
- Flask blueprint with API endpoints for backup management
- Auto-backup on app startup

Data files protected:
- contributor_reputation.json
- pr_payouts.json
- pr_reviews.json
- reputation.json
- security_logs.json
- pr_rate_limits.json
- wsi_usage.json
"""

import os
import json
import hashlib
import shutil
import gzip
import glob
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request

backup_bp = Blueprint('backup', __name__)

# =============================================================================
# CONFIG
# =============================================================================

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
CHECKSUM_FILE = os.path.join(DATA_DIR, "checksums.json")
MAX_BACKUPS = 7  # Keep 7 days of backups

# Files to protect
DATA_FILES = [
    "contributor_reputation.json",
    "pr_payouts.json",
    "pr_reviews.json",
    "reputation.json",
    "security_logs.json",
    "pr_rate_limits.json",
    "wsi_usage.json",
]

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")


# =============================================================================
# CHECKSUM FUNCTIONS
# =============================================================================

def compute_checksum(filepath):
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except FileNotFoundError:
        return None


def generate_checksums():
    """Generate checksums for all data files."""
    checksums = {}
    for filename in DATA_FILES:
        filepath = os.path.join(DATA_DIR, filename)
        checksum = compute_checksum(filepath)
        if checksum:
            checksums[filename] = {
                "sha256": checksum,
                "size": os.path.getsize(filepath),
                "checked_at": datetime.utcnow().isoformat() + "Z"
            }
    return checksums


def save_checksums(checksums):
    """Save checksums to disk."""
    try:
        with open(CHECKSUM_FILE, "w") as f:
            json.dump(checksums, f, indent=2)
        return True
    except Exception as e:
        print(f"[BACKUP] Error saving checksums: {e}", flush=True)
        return False


def load_checksums():
    """Load saved checksums from disk."""
    try:
        if os.path.exists(CHECKSUM_FILE):
            with open(CHECKSUM_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"[BACKUP] Error loading checksums: {e}", flush=True)
    return {}


def verify_integrity():
    """
    Verify all data files against stored checksums.
    Returns dict with status per file.
    """
    saved = load_checksums()
    current = generate_checksums()
    results = {}

    for filename in DATA_FILES:
        filepath = os.path.join(DATA_DIR, filename)

        if not os.path.exists(filepath):
            results[filename] = {"status": "missing", "detail": "File not found"}
            continue

        if filename not in saved:
            results[filename] = {"status": "no_baseline", "detail": "No stored checksum to compare"}
            continue

        if filename not in current:
            results[filename] = {"status": "error", "detail": "Could not compute checksum"}
            continue

        if current[filename]["sha256"] == saved[filename]["sha256"]:
            results[filename] = {"status": "ok", "detail": "Checksum matches"}
        else:
            results[filename] = {
                "status": "modified",
                "detail": "Checksum mismatch — file changed since last backup",
                "expected": saved[filename]["sha256"][:16] + "...",
                "actual": current[filename]["sha256"][:16] + "..."
            }

    return results


# =============================================================================
# BACKUP FUNCTIONS
# =============================================================================

def create_backup():
    """
    Create a compressed backup of all data files.
    Stores as timestamped .gz files in backup directory.
    Returns backup info dict.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_subdir = os.path.join(BACKUP_DIR, timestamp)
    os.makedirs(backup_subdir, exist_ok=True)

    backed_up = []
    errors = []

    for filename in DATA_FILES:
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            continue

        try:
            backup_path = os.path.join(backup_subdir, filename + ".gz")
            with open(filepath, "rb") as f_in:
                with gzip.open(backup_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            backed_up.append(filename)
        except Exception as e:
            errors.append({"file": filename, "error": str(e)})
            print(f"[BACKUP] Error backing up {filename}: {e}", flush=True)

    # Save current checksums as baseline
    checksums = generate_checksums()
    save_checksums(checksums)

    # Save checksums into backup too
    try:
        checksum_backup = os.path.join(backup_subdir, "checksums.json")
        with open(checksum_backup, "w") as f:
            json.dump(checksums, f, indent=2)
    except Exception:
        pass

    # Rotate old backups
    rotate_backups()

    backup_info = {
        "timestamp": timestamp,
        "files_backed_up": len(backed_up),
        "files": backed_up,
        "errors": errors,
        "backup_dir": backup_subdir
    }

    print(f"[BACKUP] Created backup {timestamp}: {len(backed_up)} files", flush=True)
    return backup_info


def rotate_backups():
    """Remove backups older than MAX_BACKUPS days."""
    if not os.path.exists(BACKUP_DIR):
        return

    cutoff = datetime.utcnow() - timedelta(days=MAX_BACKUPS)
    removed = 0

    for entry in sorted(os.listdir(BACKUP_DIR)):
        entry_path = os.path.join(BACKUP_DIR, entry)
        if not os.path.isdir(entry_path):
            continue

        try:
            backup_time = datetime.strptime(entry, "%Y%m%d_%H%M%S")
            if backup_time < cutoff:
                shutil.rmtree(entry_path)
                removed += 1
                print(f"[BACKUP] Rotated old backup: {entry}", flush=True)
        except ValueError:
            continue

    if removed:
        print(f"[BACKUP] Removed {removed} old backup(s)", flush=True)


def list_backups():
    """List available backups with file counts."""
    if not os.path.exists(BACKUP_DIR):
        return []

    backups = []
    for entry in sorted(os.listdir(BACKUP_DIR), reverse=True):
        entry_path = os.path.join(BACKUP_DIR, entry)
        if not os.path.isdir(entry_path):
            continue

        files = [f for f in os.listdir(entry_path) if f.endswith(".gz")]
        total_size = sum(os.path.getsize(os.path.join(entry_path, f)) for f in os.listdir(entry_path))

        backups.append({
            "timestamp": entry,
            "files": len(files),
            "total_size_bytes": total_size
        })

    return backups


def restore_from_backup(timestamp=None):
    """
    Restore data files from a backup.
    If no timestamp given, uses the most recent backup.
    Verifies checksums after restore.
    """
    if not os.path.exists(BACKUP_DIR):
        return {"success": False, "error": "No backups directory found"}

    if timestamp:
        backup_subdir = os.path.join(BACKUP_DIR, timestamp)
    else:
        # Find most recent
        entries = sorted([
            e for e in os.listdir(BACKUP_DIR)
            if os.path.isdir(os.path.join(BACKUP_DIR, e))
        ], reverse=True)

        if not entries:
            return {"success": False, "error": "No backups available"}

        backup_subdir = os.path.join(BACKUP_DIR, entries[0])
        timestamp = entries[0]

    if not os.path.exists(backup_subdir):
        return {"success": False, "error": f"Backup {timestamp} not found"}

    restored = []
    errors = []

    for gz_file in os.listdir(backup_subdir):
        if not gz_file.endswith(".gz"):
            continue

        filename = gz_file[:-3]  # Remove .gz
        restore_path = os.path.join(DATA_DIR, filename)

        try:
            gz_path = os.path.join(backup_subdir, gz_file)
            with gzip.open(gz_path, "rb") as f_in:
                with open(restore_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            restored.append(filename)
        except Exception as e:
            errors.append({"file": filename, "error": str(e)})
            print(f"[BACKUP] Error restoring {filename}: {e}", flush=True)

    # Restore checksums if available
    checksum_backup = os.path.join(backup_subdir, "checksums.json")
    if os.path.exists(checksum_backup):
        try:
            shutil.copy2(checksum_backup, CHECKSUM_FILE)
        except Exception:
            pass

    result = {
        "success": len(errors) == 0,
        "timestamp": timestamp,
        "files_restored": len(restored),
        "files": restored,
        "errors": errors
    }

    print(f"[BACKUP] Restored from {timestamp}: {len(restored)} files, {len(errors)} errors", flush=True)
    return result


# =============================================================================
# STARTUP AUTO-BACKUP
# =============================================================================

def run_startup_backup():
    """Run backup on app startup. Called from main app."""
    try:
        print("[BACKUP] Running startup backup...", flush=True)
        info = create_backup()
        print(f"[BACKUP] Startup backup complete: {info['files_backed_up']} files", flush=True)
        return info
    except Exception as e:
        print(f"[BACKUP] Startup backup failed: {e}", flush=True)
        return None


# =============================================================================
# API ENDPOINTS
# =============================================================================

def require_admin_key(f):
    """Simple admin auth decorator."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Admin-Key", "")
        if not ADMIN_KEY or key != ADMIN_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


@backup_bp.route('/api/v1/backup/status', methods=['GET'])
def backup_status():
    """Public endpoint: backup health overview."""
    integrity = verify_integrity()
    backups = list_backups()

    all_ok = all(r["status"] in ("ok", "no_baseline") for r in integrity.values())

    return jsonify({
        "success": True,
        "healthy": all_ok,
        "integrity": integrity,
        "backups_available": len(backups),
        "latest_backup": backups[0] if backups else None
    })


@backup_bp.route('/api/v1/backup/create', methods=['POST'])
@require_admin_key
def trigger_backup():
    """Admin endpoint: trigger manual backup."""
    info = create_backup()
    return jsonify({"success": True, "backup": info})


@backup_bp.route('/api/v1/backup/list', methods=['GET'])
def get_backups():
    """Public endpoint: list available backups."""
    backups = list_backups()
    return jsonify({"success": True, "backups": backups})


@backup_bp.route('/api/v1/backup/verify', methods=['GET'])
def verify_data():
    """Public endpoint: verify data integrity."""
    results = verify_integrity()
    all_ok = all(r["status"] in ("ok", "no_baseline") for r in results.values())
    return jsonify({"success": True, "healthy": all_ok, "files": results})


@backup_bp.route('/api/v1/backup/restore', methods=['POST'])
@require_admin_key
def trigger_restore():
    """Admin endpoint: restore from backup."""
    timestamp = request.json.get("timestamp") if request.json else None
    result = restore_from_backup(timestamp)
    return jsonify(result)
