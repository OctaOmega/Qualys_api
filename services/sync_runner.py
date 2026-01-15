import threading
import time
import logging
from datetime import datetime, timedelta
import dateutil.parser

logger = logging.getLogger(__name__)

class SyncRunner:
    def __init__(self, cert_client, state_manager, page_size=50):
        self.client = cert_client
        self.state_manager = state_manager
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
        try:
            logger.info("Starting Sync Loop")
            state = self.state_manager.get_state()
            last_date_str = state.get('last_successful_validFromDate') or "1900-01-01T00:00:00Z"
            
            # Logic: startDate = last_successful_validFromDate + 1 day
            # "If resuming mid-year, use startDate -> end of that year"
            
            current_start_date = dateutil.parser.parse(last_date_str)
            # Add 1 day to avoid overlap if we completed that day
            # But wait, "Update last_successful_validFromDate if newer."
            # If we crashes in the middle of a page, we might re-fetch some.
            # But user said: "Compute next start date = last + 1 day".
            # This assumes we save the max date ONLY when we are sure we got everything up to it?
            # Or is it "last_successful_validFromDate" from the ITEMS?
            # "For each page: Calculate max(validFromDate) across items. Update last_successful... Persist."
            # If so, resuming from +1 day is safer to avoid dupes, assuming strict inequality or dealing with same-day timestamps.
            # CertView uses timestamps. +1 day might skip items if validFrom is same day?
            # User requirement: "startDate = last_successful_validFromDate + 1 day". I will strictly follow this.
            
            # Correction: The logic requires iterating by YEAR.
            # "Fetch certificates using bounded year windows... Start from 1900-01-01... For each year Y..."
            
            # Converting to date objects for easier manipulation
            start_dt = current_start_date + timedelta(days=1)
            today = datetime.now()
            
            # We iterate year by year from start_dt.year
            current_year = start_dt.year
            target_year = today.year
            
            while current_year <= target_year and not self._stop_event.is_set():
                # Define window for this year
                # If it's the first partial year (resume), start from start_dt
                if current_year == start_dt.year:
                    year_start = start_dt
                else:
                    year_start = datetime(current_year, 1, 1)
                
                year_end = datetime(current_year, 12, 31, 23, 59, 59)
                
                # Cap at today
                if year_end > today:
                    year_end = today
                
                # Format to API expected string (e.g. ISO 8601)
                # "2023-01-01T00:00:00Z"
                start_str = year_start.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_str = year_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                
                logger.info(f"Syncing range: {start_str} to {end_str}")
                
                # Pagination Loop
                page_number = 0
                while not self._stop_event.is_set():
                    try:
                        logger.info(f"Fetching page {page_number}...")
                        data = self.client.fetch_certificates(start_str, end_str, page_number, self.page_size)
                        
                        # Data is list of objects
                        if not data:
                            logger.info("No data returned, moving to next year/chunk.")
                            break
                        
                        count_returned = len(data)
                        logger.info(f"Received {count_returned} items.")
                        
                        # Process and Save
                        normalized_certs = [self._normalize_cert(c) for c in data]
                        self.state_manager.save_certificates(normalized_certs)
                        
                        # Update progress
                        # Calculate max date
                        max_date_str = max(c['validFromDate'] for c in normalized_certs)
                        # We only update global state if this max date is > current stored max
                        # Actually, user logic: "Update last_successful_validFromDate if newer."
                        
                        total_so_far = self.state_manager.get_state()['total_records_collected']
                        new_total = total_so_far + count_returned
                        
                        self.state_manager.save_state(valid_from_date=max_date_str, total_records=new_total)
                        
                        if count_returned < self.page_size:
                             break
                        
                        page_number += 1
                        
                    except Exception as e:
                        logger.error(f"Error in sync loop: {e}")
                        # On error, we pause/break this year loop? Or retry?
                        # User says: "Safe long-running jobs... failures... restarts".
                        # If simple error, maybe wait and retry?
                        # Client already retries. If it bubbles up here, it's serious (network down, etc).
                        # We should probably stop sync so it can be resumed manually or auto-retry?
                        # For now, I will stop the loop to prevent infinite error logs.
                        self.state_manager.save_state(status="ERROR")
                        return

                current_year += 1
            
            if not self._stop_event.is_set():
                self.state_manager.save_state(status="COMPLETED")
                
        except Exception as e:
            logger.error(f"Fatal Sync Error: {e}")
            self.state_manager.save_state(status="ERROR")

    def _normalize_cert(self, raw):
        """
        Extracts required fields from raw CertView response.
        Keys: id, certhash, keySize, serialNumber, validFromDate, validToDate, 
        signatureAlgorithm, extendedValidation, selfSigned, issuer(name, org), 
        subject(name, org), assetCount, instanceCount, sources, assets[].name
        """
        # Note: Depending on actual API response, field access might need adjustment.
        # Assuming direct access based on user requirements.
        certhash = raw.get('certhash', req_field(raw, 'sha1')) # Fallback guess if certhash missing
        
        sources = raw.get('sources', [])
        if isinstance(sources, list):
            sources_str = ",".join(str(s) for s in sources)
        else:
            sources_str = str(sources)

        assets_list = raw.get('assets', [])
        asset_names = ",".join(set(a.get('name', '') for a in assets_list))
        
        return {
            'id': raw.get('id'),
            'certhash': raw.get('certhash'),
            'keySize': raw.get('keySize'),
            'serialNumber': raw.get('serialNumber'),
            'validFromDate': raw.get('validFromDate'), # Timestamps expected in ISO
            'validToDate': raw.get('validToDate'),
            'signatureAlgorithm': raw.get('signatureAlgorithm'),
            'extendedValidation': raw.get('extendedValidation'),
            'selfSigned': raw.get('selfSigned'),
            'issuer.name': raw.get('issuer', {}).get('name'),
            'issuer.organization': raw.get('issuer', {}).get('organization'),
            'subject.name': raw.get('subject', {}).get('name'),
            'subject.organization': raw.get('subject', {}).get('organization'),
            'assetCount': raw.get('assetCount'),
            'instanceCount': raw.get('instanceCount'),
            'sources': sources_str,
            'assets': asset_names
        }

def req_field(d, key):
    return d.get(key, '')
