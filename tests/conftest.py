import os
import pytest

@pytest.fixture(scope="session")
def base_url():
    url = os.getenv("WATTCOIN_API_URL", "https://api.wattcoin.org/api/v1")
    return url.rstrip("/")
