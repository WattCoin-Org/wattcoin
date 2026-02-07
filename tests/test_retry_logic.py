"""
Tests for AI verification retry logic.
"""

import pytest
import json
import os
import sys
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAiVerifySubmission:
    """Tests for ai_verify_submission function."""
    
    def test_returns_three_values(self):
        """Test that function returns (score, feedback, needs_review) tuple."""
        os.environ['AI_API_KEY'] = ''  # No key = error case
        
        from api_tasks import ai_verify_submission
        result = ai_verify_submission({}, {})
        
        assert len(result) == 3
        score, feedback, needs_review = result
        assert isinstance(score, int)
        assert isinstance(feedback, str)
        assert isinstance(needs_review, bool)
    
    def test_no_api_key_returns_needs_review(self):
        """Test that missing API key sets needs_review=True."""
        os.environ['AI_API_KEY'] = ''
        
        from api_tasks import ai_verify_submission
        score, feedback, needs_review = ai_verify_submission({}, {})
        
        assert score == 0
        assert 'unavailable' in feedback.lower()
        assert needs_review is True
    
    @patch('api_tasks.OpenAI')
    def test_successful_verification(self, mock_openai_class):
        """Test successful AI verification."""
        os.environ['AI_API_KEY'] = 'test-key'
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "SCORE: 8\nFEEDBACK: Good work!"
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        from api_tasks import ai_verify_submission
        score, feedback, needs_review = ai_verify_submission(
            {"title": "Test Task"},
            {"result": "Test result"}
        )
        
        assert score == 8
        assert feedback == "Good work!"
        assert needs_review is False
    
    @patch('api_tasks.OpenAI')
    def test_timeout_triggers_retry(self, mock_openai_class):
        """Test that timeout errors trigger retry with backoff."""
        import time
        os.environ['AI_API_KEY'] = 'test-key'
        
        # Mock to fail with timeout then succeed
        mock_client = MagicMock()
        
        call_count = [0]
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Connection timeout")
            # Succeed on third try
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 7\nFEEDBACK: Okay"
            return mock_response
        
        mock_client.chat.completions.create.side_effect = side_effect
        mock_openai_class.return_value = mock_client
        
        from api_tasks import ai_verify_submission
        
        # Patch sleep to speed up test
        with patch('time.sleep'):
            score, feedback, needs_review = ai_verify_submission(
                {"title": "Test"},
                {"result": "Result"}
            )
        
        assert call_count[0] == 3  # Should have retried
        assert score == 7
        assert needs_review is False
    
    @patch('api_tasks.OpenAI')
    def test_5xx_error_triggers_retry(self, mock_openai_class):
        """Test that 5xx errors trigger retry."""
        os.environ['AI_API_KEY'] = 'test-key'
        
        mock_client = MagicMock()
        
        # All calls fail with 503
        mock_client.chat.completions.create.side_effect = Exception("Error: 503 Service Unavailable")
        mock_openai_class.return_value = mock_client
        
        from api_tasks import ai_verify_submission
        
        with patch('time.sleep'):
            score, feedback, needs_review = ai_verify_submission(
                {"title": "Test"},
                {"result": "Result"}
            )
        
        # Should have exhausted retries
        assert mock_client.chat.completions.create.call_count == 3
        assert needs_review is True
        assert "3 attempts" in feedback
    
    @patch('api_tasks.OpenAI')
    def test_malformed_response_handled(self, mock_openai_class):
        """Test that malformed responses are handled gracefully."""
        os.environ['AI_API_KEY'] = 'test-key'
        
        # Mock empty response
        mock_response = MagicMock()
        mock_response.choices = []
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        from api_tasks import ai_verify_submission
        
        with patch('time.sleep'):
            score, feedback, needs_review = ai_verify_submission(
                {"title": "Test"},
                {"result": "Result"}
            )
        
        # Should handle malformed response
        assert needs_review is True
    
    @patch('api_tasks.OpenAI')
    def test_network_error_triggers_retry(self, mock_openai_class):
        """Test that network errors trigger retry."""
        os.environ['AI_API_KEY'] = 'test-key'
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection refused")
        mock_openai_class.return_value = mock_client
        
        from api_tasks import ai_verify_submission
        
        with patch('time.sleep'):
            score, feedback, needs_review = ai_verify_submission(
                {"title": "Test"},
                {"result": "Result"}
            )
        
        assert mock_client.chat.completions.create.call_count == 3
        assert needs_review is True
    
    @patch('api_tasks.OpenAI')
    def test_non_retryable_error_fails_immediately(self, mock_openai_class):
        """Test that non-retryable errors don't retry."""
        os.environ['AI_API_KEY'] = 'test-key'
        
        mock_client = MagicMock()
        # Invalid API key is not retryable
        mock_client.chat.completions.create.side_effect = Exception("Invalid API key")
        mock_openai_class.return_value = mock_client
        
        from api_tasks import ai_verify_submission
        
        with patch('time.sleep'):
            score, feedback, needs_review = ai_verify_submission(
                {"title": "Test"},
                {"result": "Result"}
            )
        
        # Should only try once for non-retryable errors
        assert mock_client.chat.completions.create.call_count == 1
        assert needs_review is True
    
    @patch('api_tasks.OpenAI')
    def test_timeout_parameter_passed(self, mock_openai_class):
        """Test that timeout parameter is passed to client."""
        os.environ['AI_API_KEY'] = 'test-key'
        
        from api_tasks import ai_verify_submission
        
        with patch('time.sleep'):
            try:
                ai_verify_submission(
                    {"title": "Test"},
                    {"result": "Result"},
                    timeout=60
                )
            except:
                pass
        
        # Check that OpenAI was called with timeout
        call_kwargs = mock_openai_class.call_args[1]
        assert call_kwargs.get('timeout') == 60
    
    @patch('api_tasks.OpenAI')
    def test_score_clamped_to_range(self, mock_openai_class):
        """Test that scores are clamped to 0-10 range."""
        os.environ['AI_API_KEY'] = 'test-key'
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "SCORE: 15\nFEEDBACK: Excellent!"
        
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        from api_tasks import ai_verify_submission
        score, feedback, needs_review = ai_verify_submission(
            {"title": "Test"},
            {"result": "Result"}
        )
        
        assert score == 10  # Clamped to max
        assert needs_review is False


@pytest.fixture
def client():
    """Create test client."""
    os.environ['DATA_DIR'] = '/tmp/wattcoin_test_data'
    os.environ['TASKS_FILE'] = '/tmp/wattcoin_test_data/tasks.json'
    
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    from bridge_web import app
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        yield client
    
    import shutil
    if os.path.exists('/tmp/wattcoin_test_data'):
        shutil.rmtree('/tmp/wattcoin_test_data')


def test_verify_task_pending_review_status(client):
    """Test that failed verification sets status to pending_review."""
    os.makedirs('/tmp/wattcoin_test_data', exist_ok=True)
    
    task_data = {
        "tasks": {
            "task_001": {
                "title": "Test Task",
                "status": "submitted",
                "submission": {"result": "test result"},
                "claimer_wallet": "TestWallet123"
            }
        },
        "stats": {}
    }
    
    with open('/tmp/wattcoin_test_data/tasks.json', 'w') as f:
        json.dump(task_data, f)
    
    # Mock AI to return needs_review
    with patch('api_tasks.ai_verify_submission') as mock_verify:
        mock_verify.return_value = (0, "Service unavailable", True)
        
        response = client.post('/api/v1/tasks/task_001/verify')
    
    assert response.status_code == 503
    data = json.loads(response.data)
    assert data["status"] == "pending_review"


def test_pending_review_in_valid_statuses():
    """Test that pending_review is a valid status."""
    from api_tasks import VALID_STATUSES
    assert 'pending_review' in VALID_STATUSES
