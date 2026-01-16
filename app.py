import logging
from flask import Flask, render_template, jsonify, request, send_file
import pandas as pd
import io

from config import Config
from extensions import db
from models import QualysAuthToken
from services.token_manager import get_valid_token 
from services.sync_state import SyncStateManager
from services.certview_client import CertViewClient
from services.sync_runner import SyncRunner

# Logging Setup
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('app')

app = Flask(__name__)
app.config.from_object(Config)

# Initialize Extensions
db.init_app(app)

# Initialize Services
class TokenManagerAdapter:
    def get_token(self, force_refresh=False):
        from services.token_manager import get_valid_token, refresh_token
        if force_refresh:
            return refresh_token()
        return get_valid_token()

token_mgr = TokenManagerAdapter()

state_mgr = SyncStateManager()

client = CertViewClient(
    base_url=app.config['QUALYS_BASE_URL'],
    list_endpoint=app.config['QUALYS_LIST_ENDPOINT'],
    token_manager=token_mgr,
    timeout=app.config["QUALYS_TIMEOUT_SECS"]
)

from services.inventory_mapping import InventoryMappingService

# ... existing imports ...

# Initialize Services
# ... existing initialization ...

inv_service = InventoryMappingService(app)

# Pass 'app' to SyncRunner so it can run with context
runner = SyncRunner(client, state_mgr, app, page_size=app.config['PAGE_SIZE'])

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('certificates.html')

@app.route('/inventory_mapping')
def inventory_view():
    return render_template('inventory_mapping.html')

@app.route('/api/inventory/upload', methods=['POST'])
def upload_inventory():
    if 'file' not in request.files:
        return jsonify({"message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400
    
    if file:
        success, msg = inv_service.save_mapping_data(file)
        if success:
            # Start background mapping
            start_success, start_msg = inv_service.start_mapping_process()
            return jsonify({"message": f"{msg} {start_msg}"}), 200
        else:
            return jsonify({"message": msg}), 400

@app.route('/api/inventory/status')
def inventory_status():
    return jsonify(inv_service.get_status())

@app.route('/api/status')
def get_status():
    state = state_mgr.get_state()
    return jsonify(state)

# ... rest of existing routes ...


@app.route('/api/data')
def get_data():
    certs = state_mgr.get_all_certificates()
    return jsonify(certs)

@app.route('/api/start_sync', methods=['POST'])
def start_sync():
    interval = request.json.get('interval', 'full') if request.is_json else 'full'
    success = runner.start_full_sync(interval=interval)
    if success:
        return jsonify({"message": f"{interval.capitalize()} Sync Started"}), 200
    return jsonify({"message": "Sync already running"}), 400

@app.route('/api/resume_sync', methods=['POST'])
def resume_sync():
    interval = request.json.get('interval', 'full') if request.is_json else 'full'
    success = runner.resume_sync(interval=interval)
    if success:
        return jsonify({"message": f"Sync Resumed ({interval})"}), 200
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
    
    df = pd.json_normalize(certs)
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

@app.route('/debug')
def debug_view():
    # Fetch Sync State
    sync_state = state_mgr.get_state()
    
    # Fetch Tokens
    tokens = QualysAuthToken.query.order_by(QualysAuthToken.id.desc()).all()
    
    return render_template('debug_tables.html', sync_state=sync_state, tokens=tokens)

@app.route('/api/refresh_token', methods=['POST'])
def force_refresh_token():
    try:
        token = token_mgr.get_token(force_refresh=True)
        return jsonify({"message": "Token Refreshed", "token": token[:20] + "..."}), 200
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        return jsonify({"message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
