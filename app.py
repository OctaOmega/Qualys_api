import os
import logging
from flask import Flask, render_template, jsonify, request, send_file
from dotenv import load_dotenv
import pandas as pd
import io

from services.token_manager import TokenManager
from services.sync_state import SyncStateManager
from services.certview_client import CertViewClient
from services.sync_runner import SyncRunner

# Load Env
load_dotenv()

# Config
QUALYS_BASE_URL = os.getenv('QUALYS_BASE_URL', 'https://gateway.qg1.apps.qualys.com')
QUALYS_LIST_ENDPOINT = os.getenv('QUALYS_CERTVIEW_LIST_ENDPOINT', '/certview/v2/certificates/list')
AUTH_ENDPOINT = os.getenv('QUALYS_INTERNAL_AUTH_ENDPOINT', '/auth/token')
AUTH_PAYLOAD = os.getenv('QUALYS_INTERNAL_AUTH_PAYLOAD', '{}')
PAGE_SIZE = int(os.getenv('PAGE_SIZE', 50))
TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))

# Logging Setup
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('app')

app = Flask(__name__)

# Initialize Services
# Note: In a real prod app with gunicorn multiple workers, 
# global variables for singleton services might not work well for the SyncRunner (background thread).
# But user requested "Flask + run instructions for flask run".
# Since `flask run` is often single process development server or user implicitly accepts this constraint 
# ("Sync must run in a background thread so UI remains responsive"), we use globals.
# For production with multiple workers, we'd need an external task queue (Celery/Redis).
# Given simplicity requirements ("Create a simple Flask app"), globals are acceptable.

token_mgr = TokenManager(
    auth_url=f"{QUALYS_BASE_URL}{AUTH_ENDPOINT}",
    auth_payload=AUTH_PAYLOAD
)

state_mgr = SyncStateManager()

client = CertViewClient(
    base_url=QUALYS_BASE_URL,
    list_endpoint=QUALYS_LIST_ENDPOINT,
    token_manager=token_mgr,
    timeout=TIMEOUT
)

runner = SyncRunner(client, state_mgr, page_size=PAGE_SIZE)

@app.route('/')
def index():
    return render_template('certificates.html')

@app.route('/api/status')
def get_status():
    state = state_mgr.get_state()
    return jsonify(state)

@app.route('/api/data')
def get_data():
    # Return all data for the grid
    # For large datasets, server-side pagination is better, 
    # but user requirements say "Displays all aggregated results in an HTML table" 
    # and implied client-side features via "AG Grid Community... Sort, Filter".
    # We will return list of objects.
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
    
    # Reorder columns if needed or just dump all
    # User said "Column order must match AG Grid columns"
    # I'll try to enforce a logical order based on the normalize function
    columns = [
        'id', 'certhash', 'validFromDate', 'validToDate', 'issuer.name', 'subject.name',
        'keySize', 'serialNumber', 'signatureAlgorithm', 'extendedValidation', 'selfSigned',
        'issuer.organization', 'subject.organization', 'assetCount', 'instanceCount', 
        'sources', 'assets'
    ]
    # Filter to existing columns only
    cols_to_use = [c for c in columns if c in df.columns]
    df = df[cols_to_use]
    
    output = io.BytesIO()
    # using openpyxl engine
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
