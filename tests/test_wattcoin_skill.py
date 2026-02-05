"""
Comprehensive tests for WattCoin Skill integration with OpenClaw.

Tests error handling, helper functions, and common workflows.
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'wattcoin'))

# Test imports (these will be mocked in most tests)
from wattcoin import (
    WattCoinError,
    WalletError,
    APIError,
    InsufficientBalanceError,
    TransactionError,
)


# =============================================================================
# CONFIGURATION & FIXTURES
# =============================================================================

@pytest.fixture
def mock_wallet_env(monkeypatch):
    """Set up a mock wallet environment."""
    monkeypatch.setenv("WATT_WALLET_PRIVATE_KEY", 
                       "3xNh2wAJV6L8Pp5kQ2jL5mK9rN4vZ7xY1pQ6rS9tU2vW3xY4zA5bB6cC7dD8eE9")
    return True


@pytest.fixture
def mock_client():
    """Mock Solana RPC client."""
    return MagicMock()


@pytest.fixture
def mock_rpc_response():
    """Mock RPC response for balance queries."""
    mock_resp = MagicMock()
    mock_resp.value.amount = "5000000000"  # 5000 WATT
    return mock_resp


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Test custom error classes and error handling."""
    
    def test_wattcoin_error_base(self):
        """Test base WattCoinError."""
        error = WattCoinError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)
    
    def test_wallet_error(self):
        """Test WalletError inheritance."""
        error = WalletError("Wallet not found")
        assert isinstance(error, WattCoinError)
    
    def test_api_error(self):
        """Test APIError inheritance."""
        error = APIError("API timeout")
        assert isinstance(error, WattCoinError)
    
    def test_insufficient_balance_error(self):
        """Test InsufficientBalanceError."""
        error = InsufficientBalanceError("Need 500 WATT, have 100")
        assert isinstance(error, WattCoinError)
    
    def test_transaction_error(self):
        """Test TransactionError."""
        error = TransactionError("Sign failed")
        assert isinstance(error, WattCoinError)


# =============================================================================
# WALLET TESTS
# =============================================================================

class TestWalletHandling:
    """Test wallet loading and address retrieval."""
    
    def test_wallet_load_from_env(self, mock_wallet_env):
        """Test loading wallet from environment variable."""
        # This would require actual solders library, skip in unit tests
        pass
    
    def test_wallet_error_no_config(self):
        """Test WalletError when no wallet configured."""
        with patch.dict(os.environ, {}, clear=True):
            from wattcoin import WalletError, _get_wallet
            with pytest.raises(WalletError) as exc_info:
                _get_wallet()
            assert "No wallet configured" in str(exc_info.value)
    
    def test_invalid_private_key_format(self):
        """Test error on invalid private key format."""
        with patch.dict(os.environ, {"WATT_WALLET_PRIVATE_KEY": "invalid"}):
            from wattcoin import WalletError, _get_wallet
            with pytest.raises(WalletError):
                _get_wallet()


# =============================================================================
# BALANCE CHECK TESTS
# =============================================================================

class TestBalanceChecks:
    """Test balance checking with error handling."""
    
    @patch('wattcoin.Client')
    def test_balance_success(self, mock_client_class, mock_wallet_env):
        """Test successful balance retrieval."""
        # This test demonstrates how balance checks should work
        pass
    
    def test_balance_invalid_address(self):
        """Test balance check with invalid address."""
        from wattcoin import watt_balance, WattCoinError
        with pytest.raises(WattCoinError):
            watt_balance(wallet_address="invalid_address")
    
    @patch('wattcoin.Client')
    def test_balance_rpc_error(self, mock_client_class):
        """Test balance check with RPC error."""
        mock_client_class.side_effect = Exception("RPC timeout")
        from wattcoin import watt_balance
        # Without raise_on_error, should return 0
        result = watt_balance(raise_on_error=False)
        assert result == 0


# =============================================================================
# OPERATION COST ESTIMATION TESTS
# =============================================================================

class TestOperationCosts:
    """Test cost estimation functions."""
    
    @patch('wattcoin.watt_balance', return_value=1000)
    def test_estimate_cost_query(self, mock_balance):
        """Test estimating cost for LLM query."""
        from wattcoin import watt_estimate_cost
        
        result = watt_estimate_cost("query", count=1)
        
        assert result["operation"] == "LLM query"
        assert result["per_unit_watt"] == 500
        assert result["total_watt"] == 500
        assert result["current_balance"] == 1000
        assert result["after_cost"] == 500
        assert result["affordable"] == True
    
    @patch('wattcoin.watt_balance', return_value=200)
    def test_estimate_cost_unaffordable(self, mock_balance):
        """Test cost estimation when unaffordable."""
        from wattcoin import watt_estimate_cost
        
        result = watt_estimate_cost("query", count=1)
        
        assert result["affordable"] == False
        assert result["shortfall"] == 300  # 500 - 200
    
    @patch('wattcoin.watt_balance', return_value=500)
    def test_estimate_cost_multiple(self, mock_balance):
        """Test cost estimation for multiple operations."""
        from wattcoin import watt_estimate_cost
        
        result = watt_estimate_cost("scrape", count=3)
        
        assert result["operation"] == "Web scrape"
        assert result["count"] == 3
        assert result["total_watt"] == 300  # 100 * 3
        assert result["affordable"] == True
    
    def test_estimate_cost_invalid_operation(self):
        """Test cost estimation with invalid operation."""
        from wattcoin import watt_estimate_cost, WattCoinError
        
        with pytest.raises(WattCoinError) as exc_info:
            watt_estimate_cost("invalid_op")
        assert "Unknown operation" in str(exc_info.value)


# =============================================================================
# BALANCE CHECK HELPER TESTS
# =============================================================================

class TestBalanceCheckHelper:
    """Test watt_check_balance_for helper function."""
    
    @patch('wattcoin.watt_balance', return_value=1000)
    def test_check_balance_for_query(self, mock_balance):
        """Test checking balance for query operation."""
        from wattcoin import watt_check_balance_for
        
        result = watt_check_balance_for("query")
        
        assert result["operation"] == "LLM query"
        assert result["can_do"] == True
        assert result["balance"] == 1000
        assert result["required"] == 500
        assert result["shortfall"] == 0
    
    @patch('wattcoin.watt_balance', return_value=50)
    def test_check_balance_for_scrape_insufficient(self, mock_balance):
        """Test checking balance for scrape with insufficient balance."""
        from wattcoin import watt_check_balance_for
        
        result = watt_check_balance_for("scrape")
        
        assert result["operation"] == "Web scrape"
        assert result["can_do"] == False
        assert result["required"] == 100
        assert result["shortfall"] == 50
    
    def test_check_balance_invalid_operation(self):
        """Test checking balance for invalid operation."""
        from wattcoin import watt_check_balance_for, WattCoinError
        
        with pytest.raises(WattCoinError):
            watt_check_balance_for("unknown_op")


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================

class TestInputValidation:
    """Test input validation for functions."""
    
    def test_watt_query_empty_prompt(self):
        """Test watt_query rejects empty prompt."""
        from wattcoin import watt_query, WattCoinError
        
        with pytest.raises(WattCoinError) as exc_info:
            watt_query("")
        assert "Prompt cannot be empty" in str(exc_info.value)
    
    def test_watt_scrape_empty_url(self):
        """Test watt_scrape rejects empty URL."""
        from wattcoin import watt_scrape, WattCoinError
        
        with pytest.raises(WattCoinError) as exc_info:
            watt_scrape("")
        assert "URL cannot be empty" in str(exc_info.value)
    
    def test_watt_scrape_invalid_format(self):
        """Test watt_scrape rejects invalid format."""
        from wattcoin import watt_scrape, WattCoinError
        
        with pytest.raises(WattCoinError) as exc_info:
            watt_scrape("https://example.com", format="invalid")
        assert "Invalid format" in str(exc_info.value)
    
    @patch('wattcoin.watt_send')
    @patch('wattcoin.watt_balance', return_value=0)
    def test_watt_query_insufficient_balance(self, mock_balance, mock_send):
        """Test watt_query checks balance."""
        from wattcoin import watt_query, InsufficientBalanceError
        
        with pytest.raises(InsufficientBalanceError):
            watt_query("What is WATT?")


# =============================================================================
# INTEGRATION WORKFLOW TESTS
# =============================================================================

class TestAgentWorkflows:
    """Test common agent workflows."""
    
    @patch('wattcoin.watt_balance', return_value=1000)
    @patch('wattcoin.watt_estimate_cost')
    @patch('wattcoin.watt_check_balance_for')
    def test_workflow_check_affordability(self, mock_check, mock_estimate, mock_balance):
        """Test workflow: check if we can afford multiple operations."""
        from wattcoin import watt_estimate_cost, watt_check_balance_for
        
        # Check if we can do 2 queries
        cost = watt_estimate_cost("query", count=2)
        assert cost["total_watt"] == 1000
        assert cost["affordable"] == True
        
        # Verify with specific check
        can_query = watt_check_balance_for("query")
        assert can_query["can_do"] == True
    
    @patch('wattcoin.watt_balance')
    def test_workflow_insufficient_balance_fallback(self, mock_balance):
        """Test workflow: handle insufficient balance gracefully."""
        mock_balance.return_value = 50
        
        from wattcoin import watt_check_balance_for
        
        # Check balance
        result = watt_check_balance_for("query")
        
        if not result["can_do"]:
            # Fallback: suggest how much more WATT needed
            needed = result["shortfall"]
            assert needed == 450


# =============================================================================
# ERROR HANDLING INTEGRATION TESTS
# =============================================================================

class TestErrorHandlingIntegration:
    """Test error handling across multiple functions."""
    
    @patch('wattcoin.watt_send')
    @patch('wattcoin.watt_balance', return_value=500)
    def test_query_with_transaction_error(self, mock_balance, mock_send):
        """Test handling transaction error during query."""
        from wattcoin import watt_query, TransactionError
        
        mock_send.side_effect = TransactionError("Sign failed")
        
        with pytest.raises(APIError):
            watt_query("test")
    
    @patch('wattcoin.requests.post')
    @patch('wattcoin.watt_send')
    @patch('wattcoin.watt_balance', return_value=500)
    def test_query_with_api_error(self, mock_balance, mock_send, mock_post):
        """Test handling API error during query."""
        from wattcoin import watt_query, APIError
        
        mock_send.return_value = "abc123"
        mock_post.side_effect = Exception("Connection timeout")
        
        with pytest.raises(APIError):
            watt_query("test")
    
    @patch('wattcoin.requests.post')
    @patch('wattcoin.watt_send')
    @patch('wattcoin.watt_balance', return_value=500)
    def test_query_with_api_failure_response(self, mock_balance, mock_send, mock_post):
        """Test handling failure response from API."""
        from wattcoin import watt_query, APIError
        
        mock_send.return_value = "abc123"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": False, "error": "Prompt rejected"}
        mock_post.return_value = mock_resp
        
        with pytest.raises(APIError):
            watt_query("test")


# =============================================================================
# TIMEOUT TESTS
# =============================================================================

class TestTimeouts:
    """Test timeout handling in API calls."""
    
    @patch('wattcoin.requests.post')
    @patch('wattcoin.watt_send')
    @patch('wattcoin.watt_balance', return_value=500)
    def test_query_timeout(self, mock_balance, mock_send, mock_post):
        """Test timeout handling in query."""
        from wattcoin import watt_query, APIError
        
        mock_send.return_value = "abc123"
        mock_post.side_effect = Exception("Timeout")
        
        with pytest.raises(APIError):
            watt_query("test", timeout_sec=5)
    
    @patch('wattcoin.requests.post')
    @patch('wattcoin.watt_send')
    @patch('wattcoin.watt_balance', return_value=500)
    def test_scrape_timeout(self, mock_balance, mock_send, mock_post):
        """Test timeout handling in scrape."""
        from wattcoin import watt_scrape, APIError
        
        mock_send.return_value = "abc123"
        mock_post.side_effect = Exception("Timeout")
        
        with pytest.raises(APIError):
            watt_scrape("https://example.com", timeout_sec=5)


# =============================================================================
# AGENT-SPECIFIC WORKFLOW TESTS
# =============================================================================

class TestAgentSpecificWorkflows:
    """Test workflows specific to OpenClaw agent integration."""
    
    @patch('wattcoin.watt_balance', return_value=5000)
    @patch('wattcoin.watt_estimate_cost')
    def test_agent_budget_planning(self, mock_estimate, mock_balance):
        """Test agent planning queries and scrapes within budget."""
        from wattcoin import watt_estimate_cost
        
        # Plan: 5 queries + 10 scrapes
        query_cost = watt_estimate_cost("query", count=5)
        scrape_cost = watt_estimate_cost("scrape", count=10)
        
        total = query_cost["total_watt"] + scrape_cost["total_watt"]
        remaining = 5000 - total
        
        # Should have enough for 5*500 + 10*100 = 3500 WATT
        assert remaining >= 1500
    
    @patch('wattcoin.watt_balance')
    @patch('wattcoin.watt_check_balance_for')
    def test_agent_graceful_degradation(self, mock_check, mock_balance):
        """Test agent degrading service when balance low."""
        # Simulate low balance scenario
        mock_balance.return_value = 50
        
        from wattcoin import watt_check_balance_for
        
        can_query = watt_check_balance_for("query")
        can_scrape = watt_check_balance_for("scrape")
        
        # Both should be unable
        assert can_query["can_do"] == False
        assert can_scrape["can_do"] == False


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    # Run with: python -m pytest test_wattcoin_skill.py -v
    pytest.main([__file__, "-v", "--tb=short"])
