import logging
import time
import requests
import json
import threading
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configure logging
logger = logging.getLogger(__name__)

class TokenManager:
    """
    Manages authentication tokens for the Qualys API.
    Handles caching, expiration (4 hours), and refresh (at 3.5 hours).
    Thread-safe.
    """
    def __init__(self, auth_url, auth_payload):
        self.auth_url = auth_url
        self.auth_payload = auth_payload
        self._token = None
        self._token_issue_time = 0
        self._lock = threading.Lock()
        
        # 3.5 hours in seconds = 210 minutes * 60 = 12600 seconds
        self.REFRESH_INTERVAL = 3.5 * 60 * 60 

    def get_token(self, force_refresh=False):
        """
        Returns a valid auth token.
        If the cached token is older than 3.5 hours or force_refresh is True,
        fetches a new token.
        """
        with self._lock:
            now = time.time()
            if self._token and not force_refresh:
                age = now - self._token_issue_time
                if age < self.REFRESH_INTERVAL:
                    return self._token
            
            # Fetch new token
            logger.info("Fetching new auth token...")
            self._token = self._fetch_new_token()
            self._token_issue_time = time.time()
            return self._token

    def _fetch_new_token(self):
        """
        Performs the actual API call to get a token using retries.
        """
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))

        try:
            # Determine if payload is JSON or form data based on typical Qualys usage
            # User said "QUALYS_INTERNAL_AUTH_PAYLOAD" is JSON in env vars.
            # Assuming POST with JSON body.
            headers = {'Content-Type': 'application/json'}
            if isinstance(self.auth_payload, str):
                payload = json.loads(self.auth_payload)
            else:
                payload = self.auth_payload

            response = session.post(self.auth_url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Assuming the token is in the response body text or a specific field.
            # Standard Qualys response might vary, but user didn't specify exact auth response format.
            # Common pattern: just the text, or a specific key.
            # I will assume the response TEXT is the token or it contains an 'access_token' or similar.
            # However, prompt says "Treat the initial token as invalid... Request a new token".
            # Without specific response format, I'll store the whole text or json.
            # "The CertView API requires an internal auth token."
            # Let's try to parse as JSON, if fail use text.
            try:
                data = response.json()
                if 'token' in data:
                    return data['token']
                if 'access_token' in data:
                    return data['access_token']
                return response.text # Fallback
            except ValueError:
                return response.text

        except Exception as e:
            logger.error(f"Failed to fetch auth token: {e}")
            raise
