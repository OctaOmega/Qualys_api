from datetime import datetime
from extensions import db

class QualysAuthToken(db.Model):
    __tablename__ = 'qualys_auth_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    token_value = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    valid = db.Column(db.Boolean, default=True)
    auth_url = db.Column(db.String(512), nullable=True)
    status_code = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

class SyncState(db.Model):
    __tablename__ = 'sync_state'

    id = db.Column(db.Integer, primary_key=True)
    last_successful_valid_from_date = db.Column(db.String(64), default='1900-01-01T00:00:00Z')
    last_sync_timestamp = db.Column(db.DateTime, nullable=True)
    total_records_collected = db.Column(db.Integer, default=0)
    status = db.Column(db.String(64), default='STOPPED')

class Certificate(db.Model):
    __tablename__ = 'certificates'

    id = db.Column(db.Integer, primary_key=True)
    certhash = db.Column(db.String(128), index=True)
    key_size = db.Column(db.Integer)
    serial_number = db.Column(db.String(128))
    
    valid_to_date = db.Column(db.String(64))
    valid_to = db.Column(db.BigInteger)
    valid_from_date = db.Column(db.String(64))
    valid_from = db.Column(db.BigInteger)
    
    signature_algorithm = db.Column(db.String(64))
    extended_validation = db.Column(db.Boolean)
    created_date = db.Column(db.String(64))
    
    dn = db.Column(db.Text)
    subject = db.Column(db.JSON)
    
    update_date = db.Column(db.String(64))
    last_found = db.Column(db.BigInteger)
    imported = db.Column(db.Boolean)
    self_signed = db.Column(db.Boolean)
    
    issuer = db.Column(db.JSON)
    root_issuer = db.Column(db.JSON)
    issuer_category = db.Column(db.String(128))
    
    instance_count = db.Column(db.Integer)
    asset_count = db.Column(db.Integer)
    
    sources = db.Column(db.JSON)
    assets = db.Column(db.JSON)
    
    mapped_to_mip = db.Column(db.Boolean, default=False)
    mip_status = db.Column(db.String(64), default='Unknown')

    full_json = db.Column(db.Text)

class InventoryMapping(db.Model):
    __tablename__ = 'inventory_mapping'
    
    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(128), index=True)
    certificate_name = db.Column(db.String(255))
    certificate_status = db.Column(db.String(64))
    processed = db.Column(db.Boolean, default=False)
