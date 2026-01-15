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
