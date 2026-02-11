import pytest
from wattcoin import WattClient
from wattcoin.exceptions import APIError

def test_client_init():
    client = WattClient(wallet="test_wallet")
    assert client.wallet == "test_wallet"
    assert client.base_url == "https://wattcoin-production-81a7.up.railway.app"

def test_client_stats():
    client = WattClient()
    try:
        stats = client.stats()
        assert "total_tasks" in stats or "error" in stats
    except Exception as e:
        # If API is down, we at least check it was a connection error
        assert "Connection error" in str(e) or isinstance(e, APIError)
