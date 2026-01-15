import threading
import time
import logging
from datetime import datetime, timedelta
import dateutil.parser

logger = logging.getLogger(__name__)

class SyncRunner:
    def __init__(self, cert_client, state_manager, app, page_size=50):
        self.client = cert_client
        self.state_manager = state_manager
        self.app = app
        self.page_size = page_size
        self._stop_event = threading.Event()
        self._thread = None

    def start_full_sync(self):
        """Starts a fresh sync from 1900-01-01."""
        if self.is_running():
            logger.warning("Sync already running.")
            return False
        
        self.state_manager.clear_data()
        self._stop_event.clear()
        
        # Initial State
        self.state_manager.save_state(
            valid_from_date="1900-01-01T00:00:00Z",
            total_records=0,
            status="RUNNING"
        )
        
        self._thread = threading.Thread(target=self._run_sync_loop)
        self._thread.start()
        return True

    def resume_sync(self):
        """Resumes sync from last successful date."""
        if self.is_running():
            logger.warning("Sync already running.")
            return False
        
        self._stop_event.clear()
        self.state_manager.save_state(status="RUNNING")
        
        self._thread = threading.Thread(target=self._run_sync_loop)
        self._thread.start()
        return True

    def stop_sync(self):
        """Signals the sync loop to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.state_manager.save_state(status="STOPPED")

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _run_sync_loop(self):
        # IMPORTANT: Run inside app context for DB access
        with self.app.app_context():
            try:
                logger.info("Starting Sync Loop")
                state = self.state_manager.get_state()
                last_date_str = state.get('last_successful_validFromDate') or "1900-01-01T00:00:00Z"
                
                current_start_date = dateutil.parser.parse(last_date_str)
                current_start_date = dateutil.parser.parse(last_date_str)
                # Next start date logic
                start_dt = current_start_date + timedelta(days=1)
                today = datetime.now()
                
                current_year = start_dt.year
                target_year = today.year
                
                while current_year <= target_year and not self._stop_event.is_set():
                    if current_year == start_dt.year:
                        year_start = start_dt
                    else:
                        year_start = datetime(current_year, 1, 1)
                    
                    year_end = datetime(current_year, 12, 31, 23, 59, 59)
                    if year_end > today:
                        year_end = today
                    
                    start_str = year_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                    end_str = year_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                    
                    logger.info(f"Syncing range: {start_str} to {end_str}")
                    
                    page_number = 0
                    while not self._stop_event.is_set():
                        try:
                            logger.info(f"Fetching page {page_number}...")
                            data = self.client.fetch_certificates(start_str, end_str, page_number, self.page_size)
                            
                            if not data:
                                logger.info("No data returned, moving to next year/chunk.")
                                break
                            
                            count_returned = len(data)
                            logger.info(f"Received {count_returned} items.")
                            
                            normalized_certs = [self._normalize_cert(c) for c in data]
                            self.state_manager.save_certificates(normalized_certs)
                            
                            # Calculate max date for state
                            if normalized_certs:
                                max_date_str = max(c['validFromDate'] for c in normalized_certs)
                                total_so_far = self.state_manager.get_state()['total_records_collected']
                                new_total = total_so_far + count_returned
                                self.state_manager.save_state(valid_from_date=max_date_str, total_records=new_total)
                            
                            if count_returned < self.page_size:
                                 break
                            
                            page_number += 1
                            
                        except Exception as e:
                            logger.error(f"Error in sync loop: {e}")
                            self.state_manager.save_state(status="ERROR")
                            return

                    current_year += 1
                
                if not self._stop_event.is_set():
                    self.state_manager.save_state(status="COMPLETED")
                    
            except Exception as e:
                logger.error(f"Fatal Sync Error: {e}")
                self.state_manager.save_state(status="ERROR")

    def _normalize_cert(self, raw):
        # We want to store the full raw response, but ensure 'id' works.
        # Fallback for certhash/sha1 if needed.
        if 'certhash' not in raw and 'sha1' in raw:
            raw['certhash'] = raw['sha1']
        
        # Ensure we don't return data without ID?
        # The caller (save_certificates) checks for 'id'.
        
        return raw
