# WattCoin API Test Suite

This is a pytest-based test suite for the WattCoin API.

## Requirements

- Python 3.x
- `pytest`
- `requests`

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements-test.txt
   ```

2. Set the base URL environment variable (optional, defaults to `https://api.wattcoin.org/api/v1`):
   ```bash
   # Windows
   set WATTCOIN_API_URL=https://api.wattcoin.org/api/v1
   
   # Linux/macOS
   export WATTCOIN_API_URL=https://api.wattcoin.org/api/v1
   ```

## Running Tests

Run all tests:
```bash
pytest
```

Run tests for a specific endpoint:
```bash
pytest tests/test_tasks.py
```

## Coverage

The following GET endpoints are covered:
- `/tasks`
- `/bounties`
- `/solutions`
- `/stats`
- `/pricing`
- `/reputation`
- `/nodes`
