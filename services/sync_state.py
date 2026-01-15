import json
import os
import threading
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

class SyncStateManager:
    """
    Manages persistence of the synchronization state and certificate data.
    Uses SQLite for robust storage of certificates and metadata.
    """
    def __init__(self, db_path='certificates.db'):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.init_db()

    def init_db(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Table for Sync State
            c.execute('''CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )''')
            
            # Table for Certificates
            # Table for Certificates
            c.execute('''CREATE TABLE IF NOT EXISTS certificates (
                id TEXT PRIMARY KEY,
                certhash TEXT,
                validFromDate TEXT,
                full_json TEXT
            )''')
            
            conn.commit()
            conn.close()

    def get_state(self):
        """
        Returns a dict with state:
        last_successful_validFromDate
        last_sync_timestamp
        total_records_collected
        status
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            state = {
                'last_successful_validFromDate': '1900-01-01T00:00:00Z',
                'last_sync_timestamp': None,
                'total_records_collected': 0,
                'status': 'STOPPED'
            }
            try:
                c.execute("SELECT value FROM sync_state WHERE key='state'")
                row = c.fetchone()
                if row:
                    saved_state = json.loads(row[0])
                    state.update(saved_state)
            except Exception as e:
                logger.error(f"Error reading state: {e}")
            finally:
                conn.close()
            return state

    def save_state(self, valid_from_date=None, total_records=None, status=None):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Read current first to update only changed fields
            current_state = {}
            c.execute("SELECT value FROM sync_state WHERE key='state'")
            row = c.fetchone()
            if row:
                current_state = json.loads(row[0])
            
            if valid_from_date:
                current_state['last_successful_validFromDate'] = valid_from_date
            if total_records is not None:
                current_state['total_records_collected'] = total_records
            if status:
                current_state['status'] = status
            
            current_state['last_sync_timestamp'] = datetime.now().isoformat()
            
            c.execute("INSERT OR REPLACE INTO sync_state (key, value) VALUES ('state', ?)", (json.dumps(current_state),))
            conn.commit()
            conn.close()

    def save_certificates(self, certs):
        """
        Batch insert/update certificates.
        certs: list of dicts (normalized certificate objects)
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            try:
                data = []
                for cert in certs:
                    # cert must have 'id'
                    cert_id = str(cert.get('id', ''))
                    certhash = cert.get('certhash', '')
                    valid_from = cert.get('validFromDate', '')
                    json_str = json.dumps(cert)
                    data.append((cert_id, certhash, valid_from, json_str))
                
                c.executemany("INSERT OR REPLACE INTO certificates (id, certhash, validFromDate, full_json) VALUES (?, ?, ?, ?)", data)
                conn.commit()
            except Exception as e:
                logger.error(f"Error saving certificates: {e}")
                raise
            finally:
                conn.close()

    def get_all_certificates(self):
        """
        Retrieve all certificates for display/export.
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            # Use a dict factory for better usage
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT full_json FROM certificates ORDER BY validFromDate DESC")
            rows = c.fetchall()
            conn.close()
            
            return [json.loads(r['full_json']) for r in rows]

    def clear_data(self):
        """
        Clears all data and resets state.
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM certificates")
            c.execute("DELETE FROM certificates")
            c.execute("DELETE FROM sync_state")
            conn.commit()
            conn.close()
