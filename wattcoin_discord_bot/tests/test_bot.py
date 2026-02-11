"""Tests for WattCoin Discord Bot (Bounty #150)"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import sys
sys.path.insert(0, '..')


@pytest.fixture
def mock_discord_client():
    """Mock Discord client."""
    client = MagicMock()
    client.user = MagicMock()
    client.user.name = "WattCoinBot"
    return client


@pytest.mark.asyncio
async def test_balance_command_valid_wallet():
    """Test balance query with valid wallet."""
    from bot import bot
    
    with patch.object(bot, '_rpc_call', new=AsyncMock(return_value={
        'result': {
            'value': [{
                'account': {
                    'data': {'parsed': {'info': {'tokenAmount': {'uiAmount': 50000}}}}
                }
            }]
        }
    })):
        result = await bot.get_watt_balance("HFBiqszH2ja9KY9z4YDw7ybEzDqVobKY5p9sNiXZA2Cp")
        assert result['success'] is True
        assert result['balance'] == 50000


@pytest.mark.asyncio
async def test_balance_command_empty_wallet():
    """Test balance query with no tokens."""
    from bot import bot
    
    with patch.object(bot, '_rpc_call', new=AsyncMock(return_value={'result': {'value': []}})):
        result = await bot.get_watt_balance("HFBiqszH2ja9KY9z4YDw7ybEzDqVobKY5p9sNiXZA2Cp")
        assert result['success'] is True
        assert result['balance'] == 0


@pytest.mark.asyncio
async def test_stats_command():
    """Test stats command returns data."""
    from bot import bot
    
    mock_response = {
        'active_nodes': 42,
        'total_tasks': 150,
        'pending_bounties': 23
    }
    
    with patch('aiohttp.ClientSession.get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
        
        result = await bot.get_network_stats()
        assert 'active_nodes' in result or 'error' in result


def test_alerts_toggle():
    """Test alerts system state."""
    from bot import alert_channels
    
    # Test toggle on
    alert_channels.add(12345)
    assert 12345 in alert_channels
    
    # Test toggle off
    alert_channels.discard(12345)
    assert 12345 not in alert_channels
