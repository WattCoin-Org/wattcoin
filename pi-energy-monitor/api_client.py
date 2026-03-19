"""
API client for sending energy reports to WattCoin backend
"""

import time
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class EnergyAPIClient:
    """Client for WattCoin Energy API"""
    
    def __init__(
        self,
        base_url: str,
        endpoint: str,
        wallet_address: str,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 5
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.wallet_address = wallet_address
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "PiEnergyMonitor/1.0.0"
        })
    
    @property
    def api_url(self) -> str:
        """Full API URL"""
        return f"{self.base_url}{self.endpoint}"
    
    def send_report(self, report: dict) -> bool:
        """Send energy report to API with retry logic"""
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    self.api_url,
                    json=report,
                    timeout=self.timeout
                )
                
                # Check response
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get("success"):
                            logger.debug(f"API accepted report: {data}")
                            return True
                        else:
                            logger.warning(f"API rejected report: {data.get('error')}")
                            # Don't retry on rejection
                            return False
                    except ValueError:
                        # No JSON, but 200 OK - assume success
                        return True
                        
                elif response.status_code >= 500:
                    # Server error - retry
                    logger.warning(f"API server error ({response.status_code}), attempt {attempt + 1}/{self.max_retries}")
                    last_error = f"Server error: {response.status_code}"
                    
                elif response.status_code >= 400:
                    # Client error - don't retry
                    logger.error(f"API client error: {response.status_code} - {response.text}")
                    return False
                    
                else:
                    # Other status codes
                    logger.warning(f"API returned {response.status_code}")
                    last_error = f"HTTP {response.status_code}"
                
            except requests.Timeout:
                logger.warning(f"API timeout (attempt {attempt + 1}/{self.max_retries})")
                last_error = "Request timeout"
                
            except requests.ConnectionError as e:
                logger.warning(f"API connection error (attempt {attempt + 1}/{self.max_retries}): {e}")
                last_error = f"Connection error: {e}"
                
            except Exception as e:
                logger.error(f"Unexpected API error: {e}")
                last_error = str(e)
                break
            
            # Wait before retry
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        logger.error(f"Failed to send report after {self.max_retries} attempts: {last_error}")
        return False
    
    def test_connection(self) -> tuple[bool, str]:
        """Test API connection"""
        try:
            # Try to reach the base URL
            response = self.session.get(
                self.base_url,
                timeout=10
            )
            
            if response.status_code < 500:
                return True, "Connection successful"
            else:
                return False, f"Server error: {response.status_code}"
                
        except requests.Timeout:
            return False, "Connection timeout"
        except requests.ConnectionError as e:
            return False, f"Connection failed: {e}"
        except Exception as e:
            return False, f"Error: {e}"
    
    def close(self):
        """Close session"""
        self.session.close()
