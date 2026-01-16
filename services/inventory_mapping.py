
import threading
import pandas as pd
import logging
from extensions import db
from models import InventoryMapping, Certificate
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

class InventoryMappingService:
    def __init__(self, app):
        self.app = app
        self._thread = None
        self._is_running = False

    def save_mapping_data(self, file_path):
        """
        Reads Excel file, truncates InventoryMapping table, and saves new data.
        Returns (success, message)
        """
        try:
            # Read Excel
            df = pd.read_excel(file_path)
            
            # Normalize columns (strip spaces, lowercase)
            df.columns = df.columns.str.strip().str.lower()
            
            # Expected columns check
            required_cols = ['certificate serial number', 'certificate name', 'certificate status']
            missing = [col for col in required_cols if col not in df.columns]
            
            if missing:
                return False, f"Missing columns: {', '.join(missing)}"
            
            # Truncate Table
            InventoryMapping.query.delete()
            db.session.commit()
            
            # Insert new data
            mappings = []
            for _, row in df.iterrows():
                mapping = InventoryMapping(
                    serial_number=str(row['certificate serial number']).strip(),
                    certificate_name=str(row['certificate name']).strip(),
                    certificate_status=str(row['certificate status']).strip()
                )
                mappings.append(mapping)
            
            db.session.bulk_save_objects(mappings)
            db.session.commit()
            
            return True, f"Successfully imported {len(mappings)} records."
            
        except Exception as e:
            logger.error(f"Error saving mapping data: {e}")
            db.session.rollback()
            return False, str(e)

    def start_mapping_process(self):
        """
        Starts the background mapping process in a separate thread.
        """
        if self._thread and self._thread.is_alive():
            return False, "Mapping process is already running."
            
        self._is_running = True
        self._thread = threading.Thread(target=self._run_mapping_loop)
        self._thread.start()
        return True, "Mapping process started."

    def _run_mapping_loop(self):
        """
        Iterates through InventoryMapping and updates Certificates.
        """
        with self.app.app_context():
            try:
                logger.info("Starting Inventory Mapping Background Process")
                
                # Fetch all mappings
                mappings = InventoryMapping.query.all()
                total = len(mappings)
                processed_count = 0
                
                for mapping in mappings:
                    if not self._is_running:
                        break

                    # Logic: Find qualys cert by serial number
                    # Only define query once for strict serial match
                    cert = Certificate.query.filter_by(serial_number=mapping.serial_number).first()
                    
                    if cert:
                        # Only update if not already mapped (as per requirement: "once mapped is permanent")
                        if not cert.mapped_to_mip:
                            cert.mapped_to_mip = True
                            cert.mip_status = mapping.certificate_status
                            # mapping.processed = True # Optional: if we want to track back
                            
                            try:
                                db.session.commit()
                            except Exception as e:
                                logger.error(f"Error updating cert {cert.id}: {e}")
                                db.session.rollback()
                    
                    processed_count += 1
                
                logger.info("Inventory Mapping Process Completed")
            
            except Exception as e:
                logger.error(f"Fatal error in mapping loop: {e}")
            finally:
                self._is_running = False

    def get_status(self):
        return {
            "is_running": self._is_running
        }
