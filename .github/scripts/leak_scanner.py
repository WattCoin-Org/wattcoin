#!/usr/bin/env python3
"""
WattCoin Leak Prevention Scanner
Scans for accidentally leaked secrets, personal info, and internal URLs.
Runs as GitHub Actions workflow on every push and PR.
"""

import re
import os
import sys
import subprocess
from pathlib import Path

# =============================================================================
# PATTERN DEFINITIONS
# =============================================================================

# CRITICAL — Block immediately
API_KEY_PATTERNS = [
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub PAT'),
    (r'sk-ant-api[a-zA-Z0-9_-]{20,}', 'Anthropic API key'),
    (r'xai-[a-zA-Z0-9]{20,}', 'xAI/Grok API key'),
    (r'moltbook_sk_[a-zA-Z0-9_-]{10,}', 'Moltbook API key'),
    (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI-style API key'),
    (r'AKIA[0-9A-Z]{16}', 'AWS access key'),
    (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', 'Private key'),
]

PRIVATE_KEY_PATTERNS = [
    (r'\b[1-9A-HJ-NP-Za-km-z]{87,88}\b', 'Solana private key (base58)'),
]

PERSONAL_NAME_PATTERNS = [
    (r'\bchris\b', 'Personal name: Chris'),
    (r'\bchristopher\b', 'Personal name: Christopher'),
]

EMAIL_PATTERNS = [
    (r'[a-zA-Z0-9._%+-]+@(gmail|outlook|hotmail|yahoo|protonmail)\.[a-zA-Z]{2,}', 'Personal email'),
]

# HIGH — Block
INTERNAL_URL_PATTERNS = [
    (r'wattcoin-production[a-z0-9-]*\.up\.railway\.app', 'Railway backend URL'),
    (r'[a-z0-9]{20,}\.proxy\.runpod\.net', 'RunPod gateway URL'),
    (r'railway\.app/project/', 'Railway dashboard link'),
]

VENDOR_PATTERNS = [
    (r'\bgrok\b', 'Vendor name: Grok'),
    (r'\banthrop', 'Vendor name: Anthropic'),
    (r'\bpetals\b', 'Vendor name: Petals'),
    (r'\brunpod\b', 'Vendor name: RunPod'),
]

# MEDIUM — Warn only
PHONE_PATTERNS = [
    (r'\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}', 'Phone number'),
]

# Severity levels
CRITICAL_PATTERNS = API_KEY_PATTERNS + PRIVATE_KEY_PATTERNS + PERSONAL_NAME_PATTERNS + EMAIL_PATTERNS
HIGH_PATTERNS = INTERNAL_URL_PATTERNS + VENDOR_PATTERNS
WARNING_PATTERNS = PHONE_PATTERNS

# =============================================================================
# FILE HANDLING
# =============================================================================

SKIP_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', 
    '.woff', '.woff2', '.ttf', '.eot', '.lock', '.map',
    '.pyc', '.pyo', '.so', '.dylib', '.dll'
}

SKIP_PATHS = {
    'node_modules/', 'dist/', 'build/', '.git/', 
    '__pycache__/', '.pytest_cache/', 'venv/', '.venv/'
}

SCAN_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.md', '.txt', 
    '.html', '.css', '.yml', '.yaml', '.json', '.toml', 
    '.cfg', '.ini', '.sh', '.env', '.example'
}

# Files that contain patterns as definitions, not leaks
SCANNER_FILES = {
    '.github/scripts/leak_scanner.py',
    '.github/workflows/leak-scan.yml',
    'security_scanner.py',
}


def get_changed_files():
    """Get files to scan based on git context."""
    # Check if this is a PR
    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')
    
    # Push to main — diff against parent
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1..HEAD"],
        capture_output=True, text=True, check=False
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split('\n')
    
    # Fallback — scan all tracked files
    print("⚠️  Git diff failed, falling back to full repo scan", file=sys.stderr)
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        return result.stdout.strip().split('\n')
    
    # Ultimate fallback - scan current directory
    print("⚠️  Git commands unavailable, scanning current directory", file=sys.stderr)
    all_files = []
    for root, dirs, files in os.walk('.'):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not any(skip in d for skip in SKIP_PATHS)]
        for file in files:
            filepath = os.path.join(root, file)
            all_files.append(filepath)
    return all_files


def should_scan_file(filepath):
    """Check if file should be scanned based on extension and path."""
    # Skip scanner files themselves
    if filepath in SCANNER_FILES:
        return False
    
    # Skip excluded directories
    if any(skip in filepath for skip in SKIP_PATHS):
        return False
    
    # Skip binary files
    ext = Path(filepath).suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return False
    
    # Only scan known text file extensions
    if ext not in SCAN_EXTENSIONS and ext != '':
        return False
    
    # Check if file exists and is readable
    if not os.path.isfile(filepath):
        return False
    
    return True

# =============================================================================
# EXCEPTION HANDLING
# =============================================================================

def is_env_var_lookup(line):
    """Check if line is an environment variable lookup."""
    env_patterns = [
        r'os\.getenv\s*\(',
        r'os\.environ\s*\[',
        r'os\.environ\.get\s*\(',
        r'process\.env\.',
        r'\$\{.*\}',  # Shell variable substitution
        r'ENV\[',
    ]
    return any(re.search(pattern, line) for pattern in env_patterns)


def is_import_statement(line):
    """Check if line is an import statement."""
    import_patterns = [
        r'^\s*import\s+',
        r'^\s*from\s+\w+\s+import\s+',
        r'require\s*\(',
    ]
    return any(re.search(pattern, line) for pattern in import_patterns)


def is_dependency_file(filepath):
    """Check if file is a dependency/package definition."""
    dependency_files = {
        'package.json', 'package-lock.json',
        'requirements.txt', 'requirements-test.txt',
        'Pipfile', 'Pipfile.lock', 'poetry.lock',
        'yarn.lock', 'pnpm-lock.yaml'
    }
    filename = os.path.basename(filepath)
    return filename in dependency_files


def is_test_placeholder(match_text):
    """Check if matched text is a test/example placeholder."""
    placeholders = [
        'your_api_key_here', 'YOUR_API_KEY', 'xxx', 'yyy',
        'test_key', 'example_key', 'dummy_key', 'fake_key',
        'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
    ]
    return any(placeholder in match_text.lower() for placeholder in placeholders)


def is_exception(match, line, filepath, pattern_type):
    """Check if a match is a known false positive."""
    match_text = match.group(0)
    
    # API Key exceptions
    if pattern_type == 'api_key':
        if is_env_var_lookup(line):
            return True
        if is_test_placeholder(match_text):
            return True
        # Allow key format descriptions in comments
        if line.strip().startswith('#') or line.strip().startswith('//'):
            return True
    
    # Vendor name exceptions
    if pattern_type == 'vendor':
        if is_import_statement(line):
            return True
        if is_dependency_file(filepath):
            return True
        # Allow in comments if it's generic
        if line.strip().startswith('#') or line.strip().startswith('//'):
            if 'provider' in line.lower() or 'framework' in line.lower():
                return True
    
    # Personal name exceptions
    if pattern_type == 'personal_name':
        # Allow in git commit messages (can't change history)
        if 'commit' in filepath.lower() or 'changelog' in filepath.lower():
            return True
        # Allow common compound words
        if 'christmas' in line.lower() or 'chris_cross' in line.lower():
            return True
    
    # Email exceptions
    if pattern_type == 'email':
        # Allow project/generic emails
        if 'contact@' in match_text or 'support@' in match_text or 'hello@' in match_text:
            return True
    
    return False

# =============================================================================
# SCANNING
# =============================================================================

def mask_secret(text):
    """Mask a secret for display."""
    if len(text) <= 12:
        return text[:4] + "****"
    return text[:4] + "..." + text[-4:]


def scan_line(line, line_num, filepath, patterns, pattern_type):
    """Scan a line for patterns, return findings."""
    findings = []
    
    for pattern, description in patterns:
        # Use case-insensitive for personal names
        flags = re.IGNORECASE if pattern_type == 'personal_name' else 0
        
        for match in re.finditer(pattern, line, flags=flags):
            # Check exceptions
            if is_exception(match, line, filepath, pattern_type):
                continue
            
            match_text = match.group(0)
            
            # Mask secrets in output
            if pattern_type in ['api_key', 'private_key']:
                display_text = mask_secret(match_text)
            else:
                display_text = match_text
            
            findings.append({
                'filepath': filepath,
                'line_num': line_num,
                'description': description,
                'match': display_text,
                'pattern_type': pattern_type
            })
    
    return findings


def scan_file(filepath):
    """Scan a single file against all patterns."""
    findings = {
        'critical': [],
        'high': [],
        'warnings': []
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"⚠️  Could not read {filepath}: {e}", file=sys.stderr)
        return findings
    
    for line_num, line in enumerate(lines, start=1):
        # Scan CRITICAL patterns
        findings['critical'].extend(
            scan_line(line, line_num, filepath, CRITICAL_PATTERNS, 'api_key')
        )
        
        # Scan HIGH patterns
        findings['high'].extend(
            scan_line(line, line_num, filepath, INTERNAL_URL_PATTERNS, 'internal_url')
        )
        findings['high'].extend(
            scan_line(line, line_num, filepath, VENDOR_PATTERNS, 'vendor')
        )
        
        # Scan WARNING patterns
        findings['warnings'].extend(
            scan_line(line, line_num, filepath, WARNING_PATTERNS, 'phone')
        )
    
    return findings

# =============================================================================
# OUTPUT
# =============================================================================

def format_results(all_findings):
    """Format and print results, return exit code."""
    critical = all_findings['critical']
    high = all_findings['high']
    warnings = all_findings['warnings']
    
    total_blocking = len(critical) + len(high)
    
    # Success case
    if total_blocking == 0 and len(warnings) == 0:
        print("✅ Leak scan passed — no issues found")
        return 0
    
    # Warning-only case
    if total_blocking == 0 and len(warnings) > 0:
        print("✅ Leak scan passed with warnings\n")
        print("WARNINGS:")
        for finding in warnings:
            print(f"  {finding['filepath']}:{finding['line_num']} — {finding['description']}: {finding['match']}")
        print(f"\nTotal: 0 blocking issues, {len(warnings)} warning(s)")
        return 0
    
    # Failure case
    print("🚨 LEAK PREVENTION SCAN FAILED\n")
    
    if critical:
        print("CRITICAL:")
        for finding in critical:
            print(f"  {finding['filepath']}:{finding['line_num']} — {finding['description']}: {finding['match']}")
        print()
    
    if high:
        print("HIGH:")
        for finding in high:
            print(f"  {finding['filepath']}:{finding['line_num']} — {finding['description']}: {finding['match']}")
        print()
    
    if warnings:
        print("WARNINGS:")
        for finding in warnings:
            print(f"  {finding['filepath']}:{finding['line_num']} — {finding['description']}: {finding['match']}")
        print()
    
    print(f"Total: {total_blocking} blocking issue(s), {len(warnings)} warning(s)")
    print("❌ Fix all CRITICAL and HIGH issues before merging")
    
    return 1

# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point."""
    print("🔍 WattCoin Leak Prevention Scanner")
    print("=" * 60)
    
    # Get files to scan
    files = get_changed_files()
    scannable_files = [f for f in files if should_scan_file(f)]
    
    print(f"📂 Found {len(files)} changed file(s), {len(scannable_files)} scannable")
    print()
    
    # Scan files
    all_findings = {
        'critical': [],
        'high': [],
        'warnings': []
    }
    
    for filepath in scannable_files:
        file_findings = scan_file(filepath)
        all_findings['critical'].extend(file_findings['critical'])
        all_findings['high'].extend(file_findings['high'])
        all_findings['warnings'].extend(file_findings['warnings'])
    
    # Format and return
    exit_code = format_results(all_findings)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

