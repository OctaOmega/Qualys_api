import json
import logging
from datetime import datetime
from extensions import db
from models import SyncState, Certificate

logger = logging.getLogger(__name__)

class SyncStateManager:
    """
    Manages persistence of the synchronization state and certificate data.
    Uses SQLAlchemy for robust storage.
    """
    def __init__(self):
        # db.create_all() is handled in app.py
        pass

    def get_state(self):
        """
        Returns a dict with state:
        last_successful_valid_from_date
        last_sync_timestamp
        total_records_collected
        status
        """
        try:
            state = SyncState.query.get(1)
            if not state:
                return {
                    'last_successful_validFromDate': '1900-01-01T00:00:00Z',
                    'last_sync_timestamp': None,
                    'total_records_collected': 0,
                    'status': 'STOPPED'
                }
            
            return {
                'last_successful_validFromDate': state.last_successful_valid_from_date,
                'last_sync_timestamp': state.last_sync_timestamp.isoformat() if state.last_sync_timestamp else None,
                'total_records_collected': state.total_records_collected,
                'status': state.status
            }
        except Exception as e:
            logger.error(f"Error reading state: {e}")
            return {
                'last_successful_validFromDate': '1900-01-01T00:00:00Z',
                'last_sync_timestamp': None,
                'total_records_collected': 0,
                'status': 'STOPPED'
            }

    def save_state(self, valid_from_date=None, total_records=None, status=None):
        try:
            state = SyncState.query.get(1)
            if not state:
                state = SyncState(id=1)
                db.session.add(state)
            
            if valid_from_date:
                state.last_successful_valid_from_date = valid_from_date
            if total_records is not None:
                state.total_records_collected = total_records
            if status:
                state.status = status
            
            state.last_sync_timestamp = datetime.now()
            db.session.commit()
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            db.session.rollback()

    def save_certificates(self, certs):
        """
        Batch insert/update certificates.
        certs: list of dicts (normalized certificate objects)
        """
        try:
            for cert_data in certs:
                cert_id = cert_data.get('id')
                if not cert_id:
                    continue
                
                # Check if exists
                cert = Certificate.query.get(cert_id)
                if not cert:
                    cert = Certificate(id=cert_id)
                    db.session.add(cert)
                
                # Update fields
                cert.certhash = cert_data.get('certhash')
                cert.key_size = cert_data.get('keySize')
                cert.serial_number = cert_data.get('serialNumber')
                cert.valid_to_date = cert_data.get('validToDate')
                cert.valid_to = cert_data.get('validTo')
                cert.valid_from_date = cert_data.get('validFromDate')
                cert.valid_from = cert_data.get('validFrom')
                cert.signature_algorithm = cert_data.get('signatureAlgorithm')
                cert.extended_validation = cert_data.get('extendedValidation')
                cert.created_date = cert_data.get('createdDate')
                cert.dn = cert_data.get('dn')
                cert.subject = cert_data.get('subject')
                cert.update_date = cert_data.get('updateDate')
                cert.last_found = cert_data.get('lastFound')
                cert.imported = cert_data.get('imported')
                cert.self_signed = cert_data.get('selfSigned')
                cert.issuer = cert_data.get('issuer')
                cert.root_issuer = cert_data.get('rootissuer')
                cert.issuer_category = cert_data.get('issuerCategory')
                cert.instance_count = cert_data.get('instanceCount')
                cert.asset_count = cert_data.get('assetCount')
                cert.sources = cert_data.get('sources')
                cert.assets = cert_data.get('assets')
                
                if 'mapped_to_mip' in cert_data:
                    cert.mapped_to_mip = cert_data['mapped_to_mip']
                if 'mip_status' in cert_data:
                    cert.mip_status = cert_data['mip_status']

                cert.full_json = json.dumps(cert_data)
            
            db.session.commit()
        except Exception as e:
            logger.error(f"Error saving certificates: {e}")
            db.session.rollback()
            raise

    def get_all_certificates(self):
        """
        Retrieve all certificates for display/export.
        """
        try:
            certs = Certificate.query.order_by(Certificate.valid_from_date.desc()).all()
            results = []
            for c in certs:
                if c.full_json:
                    data = json.loads(c.full_json)
                else:
                    data = {} # Should have full_json always, but handle gracefully
                    
                # Ensure local fields are merged/overwrite if needed
                data['id'] = c.id
                data['mapped_to_mip'] = c.mapped_to_mip
                data['mip_status'] = c.mip_status
                results.append(data)
                
            return results
        except Exception as e:
            logger.error(f"Error getting certificates: {e}")
            return []

    def clear_data(self):
        """
        Clears all data and resets state.
        """
        try:
            Certificate.query.delete()
            SyncState.query.delete()
            db.session.commit()
        except Exception as e:
            logger.error(f"Error clearing data: {e}")
            db.session.rollback()
