import os
import logging
from flask import Flask, render_template, jsonify, request, send_file
from dotenv import load_dotenv
import pandas as pd
import io
import json

from extensions import db
from models import QualysAuthToken
# token_manager is now a module with functions, need to adapt client usage
from services.token_manager import get_valid_token 
from services.sync_state import SyncStateManager
from services.certview_client import CertViewClient
from services.sync_runner import SyncRunner

# Load Env
load_dotenv()

# Logging Setup
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('app')

app = Flask(__name__)

# Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mapping Env to Config expected by TokenManager
QUALYS_BASE_URL = os.getenv('QUALYS_BASE_URL', 'https://gateway.qg1.apps.qualys.com')
QUALYS_LIST_ENDPOINT = os.getenv('QUALYS_CERTVIEW_LIST_ENDPOINT', '/certview/v2/certificates/list')
AUTH_ENDPOINT = os.getenv('QUALYS_INTERNAL_AUTH_ENDPOINT', '/auth/token')
AUTH_PAYLOAD_STR = os.getenv('QUALYS_INTERNAL_AUTH_PAYLOAD', '{"username": "", "password": ""}')

# Parse payload to get user/pass for config
try:
    auth_payload = json.loads(AUTH_PAYLOAD_STR)
    username = auth_payload.get('username')
    password = auth_payload.get('password')
except:
    username = None
    password = None

app.config["QUALYS_AUTH_URL"] = f"{QUALYS_BASE_URL}{AUTH_ENDPOINT}"
app.config["QUALYS_USERNAME"] = username
app.config["QUALYS_PASSWORD"] = password
app.config["QUALYS_TIMEOUT_SECS"] = int(os.getenv('REQUEST_TIMEOUT', 60))

# Initialize Extensions
db.init_app(app)

# Initialize Services
# Note: TokenManager is now functions using 'current_app' and 'db'
# We need to wrap it or adapt CertViewClient to use it.
# CertViewClient expects an object with .get_token().
class TokenManagerAdapter:
    def get_token(self, force_refresh=False):
        # The new logic handles expiration internally in get_valid_token logic
        # But force_refresh isn't explicitly exposed in get_valid_token 
        # (it refreshes if invalid/missing).
        # We can just call get_valid_token().
        # If force_refresh is needed by Client logic (e.g. on 401),
        # get_valid_token() might return a cached valid one.
        # However, the user provided code:
        # "If token expired or none exists: refresh... Ensures expired token is marked valid=False."
        # It doesn't seemingly allow "Force Refresh even if DB says valid".
        # But Client logic calls get_token(force_refresh=True) on 401.
        # Modification: If force_refresh is True, we might want to manually 'refresh_token()'.
        # But I should stick to the user's provided functions mainly.
        # I'll import refresh_token too.
        from services.token_manager import get_valid_token, refresh_token
        if force_refresh:
            return refresh_token()
        return get_valid_token()

token_mgr = TokenManagerAdapter()

# SyncStateManager uses its own sqlite connection for Certificates.
# We might consider moving Certificates to SQLAlchemy too, but user didn't ask for that migration,
# only the Auth logic. I'll keep SyncStateManager as is for now to minimize risk suitable for "Refactor Auth".
state_mgr = SyncStateManager()

client = CertViewClient(
    base_url=QUALYS_BASE_URL,
    list_endpoint=QUALYS_LIST_ENDPOINT,
    token_manager=token_mgr,
    timeout=app.config["QUALYS_TIMEOUT_SECS"]
)

# Pass 'app' to SyncRunner so it can run with context
runner = SyncRunner(client, state_mgr, app, page_size=int(os.getenv('PAGE_SIZE', 50)))

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('certificates.html')

@app.route('/api/status')
def get_status():
    state = state_mgr.get_state()
    return jsonify(state)

@app.route('/api/data')
def get_data():
    certs = state_mgr.get_all_certificates()
    return jsonify(certs)

@app.route('/api/start_sync', methods=['POST'])
def start_sync():
    success = runner.start_full_sync()
    if success:
        return jsonify({"message": "Full Sync Started"}), 200
    return jsonify({"message": "Sync already running"}), 400

@app.route('/api/resume_sync', methods=['POST'])
def resume_sync():
    success = runner.resume_sync()
    if success:
        return jsonify({"message": "Sync Resumed"}), 200
    return jsonify({"message": "Sync already running"}), 400

@app.route('/api/stop_sync', methods=['POST'])
def stop_sync():
    runner.stop_sync()
    return jsonify({"message": "Sync Stopped"}), 200

@app.route('/api/reset_state', methods=['POST'])
def reset_state():
    if runner.is_running():
        return jsonify({"message": "Cannot clear state while running"}), 400
    state_mgr.clear_data()
    return jsonify({"message": "State Cleared"}), 200

@app.route('/api/export')
def export_excel():
    certs = state_mgr.get_all_certificates()
    if not certs:
        return jsonify({"message": "No data to export"}), 400
    
    df = pd.DataFrame(certs)
    columns = [
        'id', 'certhash', 'validFromDate', 'validToDate', 'issuer.name', 'subject.name',
        'keySize', 'serialNumber', 'signatureAlgorithm', 'extendedValidation', 'selfSigned',
        'issuer.organization', 'subject.organization', 'assetCount', 'instanceCount', 
        'sources', 'assets'
    ]
    cols_to_use = [c for c in columns if c in df.columns]
    df = df[cols_to_use]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Certificates')
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='certificates_export.xlsx'
    )

if __name__ == '__main__':
    app.run(debug=True)
