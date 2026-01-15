import requests
import logging
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class CertViewClient:
    def __init__(self, base_url, list_endpoint, token_manager, timeout=30):
        self.base_url = base_url.rstrip('/')
        self.list_endpoint = list_endpoint
        self.token_manager = token_manager
        self.timeout = timeout
        
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.mount('http://', HTTPAdapter(max_retries=retries))

    def fetch_certificates(self, start_date, end_date, page_number, page_size=50):
        """
        Fetches certificates for a given date range and page.
        Automatically handles auth and 401 retries.
        """
        url = f"{self.base_url}{self.list_endpoint}"
        
        payload = {
            "filter": {
                "filters": [
                    { "field": "certificate.type", "value": "Leaf", "operator": "EQUALS" },
                    { "field": "certificate.validFromDate", "value": start_date, "operator": "GREATER_THAN_EQUAL" },
                    { "field": "certificate.validFromDate", "value": end_date, "operator": "LESS_THAN_EQUAL" }
                ],
                "operation": "AND"
            },
            "pageNumber": page_number,
            "pageSize": page_size
        }

        # Attempt request logic
        attempts = 0
        max_attempts = 2 # 1 initial + 1 retry on 401
        
        while attempts < max_attempts:
            attempts += 1
            token = self.token_manager.get_token(force_refresh=(attempts > 1))
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Requested-With": "PyQualysApp"
            }
            
            try:
                response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
                
                if response.status_code in [401, 403]:
                    logger.warning(f"Auth failed ({response.status_code}). Retrying with new token...")
                    continue # Loop will get new token
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempts == max_attempts:
                    logger.error(f"API Request failed after {attempts} attempts: {e}")
                    raise
                time.sleep(1) # short wait before retry
        
        return []
