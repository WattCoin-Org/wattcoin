#!/usr/bin/env python3
"""
Unit tests for tip_transfer.py
Covers wallet validation, amount calculations, and transfer logic.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Import functions from tip_transfer
from tip_transfer import (
    validate_solana_address,
    load_tracker,
    save_tracker,
    add_tip,
    claim_tip,
    list_tips,
    generate_tip_message,
    generate_confirmation_message,
    mark_sent,
    WATT_DECIMALS,
    WATT_MINT,
    TRACKER_FILE,
)


class TestValidateSolanaAddress:
    """Tests for Solana address validation."""
    
    def test_valid_address(self):
        """Valid Solana addresses should return True."""
        # Real Solana addresses (32 bytes when decoded)
        valid_addresses = [
            "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
            "3bLMHWe3jNKMuKiTu1LK5a7MPBE7WN5qDwKx2s7thEkr",
            "So11111111111111111111111111111111111111112",  # Native SOL
        ]
        for addr in valid_addresses:
            assert validate_solana_address(addr) is True, f"Should be valid: {addr}"
    
    def test_invalid_address_too_short(self):
        """Addresses that are too short should return False."""
        assert validate_solana_address("short") is False
        assert validate_solana_address("abc123") is False
    
    def test_invalid_address_too_long(self):
        """Addresses that are too long should return False."""
        long_addr = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSFextra"
        assert validate_solana_address(long_addr) is False
    
    def test_invalid_address_bad_characters(self):
        """Addresses with invalid base58 characters should return False."""
        # Base58 doesn't include 0, O, I, l
        assert validate_solana_address("0vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF") is False
    
    def test_empty_address(self):
        """Empty string should return False."""
        assert validate_solana_address("") is False
    
    def test_none_address(self):
        """None should raise exception or return False."""
        try:
            result = validate_solana_address(None)
            assert result is False
        except (TypeError, AttributeError):
            pass  # Expected behavior


class TestTrackerFunctions:
    """Tests for tracker load/save operations."""
    
    @pytest.fixture
    def temp_tracker_file(self, tmp_path):
        """Create a temporary tracker file."""
        tracker_file = tmp_path / "tip_tracker.json"
        return tracker_file
    
    def test_load_tracker_creates_default(self, temp_tracker_file):
        """Loading non-existent tracker should return default structure."""
        with patch('tip_transfer.TRACKER_FILE', temp_tracker_file):
            tracker = load_tracker()
            assert "tips" in tracker
            assert "stats" in tracker
            assert tracker["tips"] == []
            assert tracker["stats"]["total_issued"] == 0
    
    def test_load_tracker_reads_existing(self, temp_tracker_file):
        """Loading existing tracker should return its contents."""
        test_data = {
            "tips": [{"tip_id": "test123", "amount": 1000}],
            "stats": {"total_issued": 1, "total_claimed": 0, "total_sent": 0, "total_watt_distributed": 0}
        }
        temp_tracker_file.write_text(json.dumps(test_data))
        
        with patch('tip_transfer.TRACKER_FILE', temp_tracker_file):
            tracker = load_tracker()
            assert len(tracker["tips"]) == 1
            assert tracker["tips"][0]["tip_id"] == "test123"
    
    def test_save_tracker_writes_file(self, temp_tracker_file):
        """Saving tracker should write to file."""
        test_data = {
            "tips": [{"tip_id": "save_test", "amount": 2000}],
            "stats": {"total_issued": 1, "total_claimed": 0, "total_sent": 0, "total_watt_distributed": 0}
        }
        
        with patch('tip_transfer.TRACKER_FILE', temp_tracker_file):
            save_tracker(test_data)
            
            # Read back and verify
            with open(temp_tracker_file, 'r') as f:
                saved = json.load(f)
            assert saved["tips"][0]["tip_id"] == "save_test"


class TestAddTip:
    """Tests for adding new tips."""
    
    @pytest.fixture
    def mock_tracker_file(self, tmp_path):
        """Create a temporary tracker file with empty state."""
        tracker_file = tmp_path / "tip_tracker.json"
        initial_data = {
            "tips": [],
            "stats": {"total_issued": 0, "total_claimed": 0, "total_sent": 0, "total_watt_distributed": 0}
        }
        tracker_file.write_text(json.dumps(initial_data))
        return tracker_file
    
    def test_add_tip_creates_new(self, mock_tracker_file):
        """Adding a tip should create new entry."""
        with patch('tip_transfer.TRACKER_FILE', mock_tracker_file):
            tip = add_tip("agent123", 5000, "comment_abc")
            
            assert tip is not None
            assert tip["recipient_agent"] == "agent123"
            assert tip["amount"] == 5000
            assert tip["comment_id"] == "comment_abc"
            assert tip["status"] == "pending"
            assert tip["claim_address"] is None
    
    def test_add_tip_increments_stats(self, mock_tracker_file):
        """Adding tips should increment total_issued."""
        with patch('tip_transfer.TRACKER_FILE', mock_tracker_file):
            add_tip("agent1", 1000, "comment1")
            add_tip("agent2", 2000, "comment2")
            
            tracker = load_tracker()
            assert tracker["stats"]["total_issued"] == 2
    
    def test_add_tip_duplicate_comment(self, mock_tracker_file):
        """Adding duplicate comment_id should return existing tip."""
        with patch('tip_transfer.TRACKER_FILE', mock_tracker_file):
            tip1 = add_tip("agent1", 1000, "same_comment")
            tip2 = add_tip("agent2", 2000, "same_comment")
            
            # Should return the original tip
            assert tip1["tip_id"] == tip2["tip_id"]
            
            # Should only have one tip
            tracker = load_tracker()
            assert len(tracker["tips"]) == 1


class TestClaimTip:
    """Tests for claiming tips."""
    
    @pytest.fixture
    def tracker_with_pending_tip(self, tmp_path):
        """Create tracker with a pending tip."""
        tracker_file = tmp_path / "tip_tracker.json"
        initial_data = {
            "tips": [{
                "tip_id": "pending123",
                "recipient_agent": "test_agent",
                "amount": 10000,
                "comment_id": "test_comment",
                "status": "pending",
                "claim_address": None,
                "claimed_at": None,
                "created_at": datetime.utcnow().isoformat(),
                "tx_signature": None,
                "sent_at": None,
                "post_id": "test_post"
            }],
            "stats": {"total_issued": 1, "total_claimed": 0, "total_sent": 0, "total_watt_distributed": 0}
        }
        tracker_file.write_text(json.dumps(initial_data))
        return tracker_file
    
    def test_claim_tip_valid_address(self, tracker_with_pending_tip):
        """Claiming with valid address should update status."""
        valid_address = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
        
        with patch('tip_transfer.TRACKER_FILE', tracker_with_pending_tip):
            tip = claim_tip("pending123", valid_address)
            
            assert tip is not None
            assert tip["status"] == "claimed"
            assert tip["claim_address"] == valid_address
            assert tip["claimed_at"] is not None
    
    def test_claim_tip_invalid_address(self, tracker_with_pending_tip):
        """Claiming with invalid address should return None."""
        with patch('tip_transfer.TRACKER_FILE', tracker_with_pending_tip):
            tip = claim_tip("pending123", "invalid_address")
            assert tip is None
    
    def test_claim_tip_not_found(self, tracker_with_pending_tip):
        """Claiming non-existent tip should return None."""
        with patch('tip_transfer.TRACKER_FILE', tracker_with_pending_tip):
            tip = claim_tip("nonexistent", "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF")
            assert tip is None
    
    def test_claim_tip_already_claimed(self, tracker_with_pending_tip):
        """Claiming already claimed tip should return existing."""
        valid_address = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
        
        with patch('tip_transfer.TRACKER_FILE', tracker_with_pending_tip):
            # First claim
            claim_tip("pending123", valid_address)
            # Second claim attempt
            tip = claim_tip("pending123", valid_address)
            
            assert tip["status"] == "claimed"


class TestMarkSent:
    """Tests for marking tips as sent."""
    
    @pytest.fixture
    def tracker_with_claimed_tip(self, tmp_path):
        """Create tracker with a claimed tip."""
        tracker_file = tmp_path / "tip_tracker.json"
        initial_data = {
            "tips": [{
                "tip_id": "claimed123",
                "recipient_agent": "test_agent",
                "amount": 10000,
                "comment_id": "test_comment",
                "status": "claimed",
                "claim_address": "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF",
                "claimed_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "tx_signature": None,
                "sent_at": None,
                "post_id": "test_post"
            }],
            "stats": {"total_issued": 1, "total_claimed": 1, "total_sent": 0, "total_watt_distributed": 0}
        }
        tracker_file.write_text(json.dumps(initial_data))
        return tracker_file
    
    def test_mark_sent_updates_status(self, tracker_with_claimed_tip):
        """Marking as sent should update status and signature."""
        tx_sig = "5xYz123abcDEFtestSignature"
        
        with patch('tip_transfer.TRACKER_FILE', tracker_with_claimed_tip):
            tip = mark_sent("claimed123", tx_sig)
            
            assert tip is not None
            assert tip["status"] == "sent"
            assert tip["tx_signature"] == tx_sig
            assert tip["sent_at"] is not None
    
    def test_mark_sent_updates_stats(self, tracker_with_claimed_tip):
        """Marking as sent should update stats."""
        with patch('tip_transfer.TRACKER_FILE', tracker_with_claimed_tip):
            mark_sent("claimed123", "test_tx_sig")
            
            tracker = load_tracker()
            assert tracker["stats"]["total_sent"] == 1
            assert tracker["stats"]["total_watt_distributed"] == 10000
    
    def test_mark_sent_not_found(self, tracker_with_claimed_tip):
        """Marking non-existent tip should return None."""
        with patch('tip_transfer.TRACKER_FILE', tracker_with_claimed_tip):
            tip = mark_sent("nonexistent", "test_tx_sig")
            assert tip is None


class TestMessageGeneration:
    """Tests for message generation functions."""
    
    def test_generate_tip_message_format(self):
        """Tip message should contain agent name and amount."""
        message = generate_tip_message("coolAgent", 50000)
        
        assert "50,000 WATT" in message
        assert "Solana address" in message.lower()
        assert "phantom.app" in message.lower()
    
    def test_generate_tip_message_large_amount(self):
        """Large amounts should be formatted with commas."""
        message = generate_tip_message("agent", 1000000)
        assert "1,000,000 WATT" in message
    
    def test_generate_confirmation_message_format(self):
        """Confirmation message should contain amount, address, and tx."""
        tx_sig = "5xYz123abcDEF"
        address = "7vvNkG3JF3JpxLEavqZSkc5T3n9hHR98Uw23fbWdXVSF"
        
        message = generate_confirmation_message(10000, address, tx_sig)
        
        assert "10,000 WATT" in message
        assert tx_sig in message
        assert "7vvN" in message  # Short address start
        assert "XVSF" in message  # Short address end
        assert "solscan.io" in message


class TestConstants:
    """Tests for constant values."""
    
    def test_watt_decimals(self):
        """WATT should have 6 decimals."""
        assert WATT_DECIMALS == 6
    
    def test_watt_mint_format(self):
        """WATT mint should be valid Solana address."""
        assert validate_solana_address(WATT_MINT) is True


class TestAmountCalculations:
    """Tests for amount calculations and edge cases."""
    
    def test_zero_amount(self, tmp_path):
        """Zero amount tips should work."""
        tracker_file = tmp_path / "tip_tracker.json"
        initial_data = {
            "tips": [],
            "stats": {"total_issued": 0, "total_claimed": 0, "total_sent": 0, "total_watt_distributed": 0}
        }
        tracker_file.write_text(json.dumps(initial_data))
        
        with patch('tip_transfer.TRACKER_FILE', tracker_file):
            tip = add_tip("agent", 0, "comment_zero")
            assert tip["amount"] == 0
    
    def test_large_amount(self, tmp_path):
        """Large amounts should be handled correctly."""
        tracker_file = tmp_path / "tip_tracker.json"
        initial_data = {
            "tips": [],
            "stats": {"total_issued": 0, "total_claimed": 0, "total_sent": 0, "total_watt_distributed": 0}
        }
        tracker_file.write_text(json.dumps(initial_data))
        
        large_amount = 1_000_000_000  # 1 billion WATT
        
        with patch('tip_transfer.TRACKER_FILE', tracker_file):
            tip = add_tip("whale", large_amount, "comment_large")
            assert tip["amount"] == large_amount


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
