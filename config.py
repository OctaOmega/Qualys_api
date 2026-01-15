import os
import json
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Qualys Base Settings
    QUALYS_BASE_URL = os.getenv('QUALYS_BASE_URL', 'https://gateway.qg1.apps.qualys.com')
    QUALYS_LIST_ENDPOINT = os.getenv('QUALYS_CERTVIEW_LIST_ENDPOINT', '/certview/v2/certificates/list')
    
    # Auth Settings
    _AUTH_ENDPOINT = os.getenv('QUALYS_INTERNAL_AUTH_ENDPOINT', '/auth/token')
    QUALYS_AUTH_URL = os.getenv('QUALYS_AUTH_URL') or f"{QUALYS_BASE_URL}{_AUTH_ENDPOINT}"
    
    # Auth Credentials
    # Prefer explicit env vars, fallback to parsing the payload JSON
    QUALYS_USERNAME = os.getenv('QUALYS_USERNAME')
    QUALYS_PASSWORD = os.getenv('QUALYS_PASSWORD')
    
    _AUTH_PAYLOAD_STR = os.getenv('QUALYS_INTERNAL_AUTH_PAYLOAD')
    if _AUTH_PAYLOAD_STR and (not QUALYS_USERNAME or not QUALYS_PASSWORD):
        try:
            _payload = json.loads(_AUTH_PAYLOAD_STR)
            if not QUALYS_USERNAME:
                QUALYS_USERNAME = _payload.get('username')
            if not QUALYS_PASSWORD:
                QUALYS_PASSWORD = _payload.get('password')
        except Exception:
            pass

    # Timeouts and Limits
    QUALYS_TIMEOUT_SECS = int(os.getenv('QUALYS_TIMEOUT_SECS') or os.getenv('REQUEST_TIMEOUT', 60))
    PAGE_SIZE = int(os.getenv('PAGE_SIZE', 50))
