import imaplib
import email
import re
import time
import logging
from typing import Optional

class EmailManager:
    """Utility to fetch OTP codes from Gmail accounts."""
    
    @staticmethod
    def get_facebook_otp(email_user: str, app_password: str, timeout: int = 120) -> Optional[str]:
        """
        Polls Gmail for the latest Facebook security code.
        """
        logging.info(f"polling_gmail_for_otp user={email_user}")
        start_time = time.time()
        
        # Poll for up to 'timeout' seconds
        while time.time() - start_time < timeout:
            try:
                # 1. Connect to Gmail IMAP
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(email_user, app_password)
                mail.select("inbox")
                
                # 2. Search for emails from Facebook security
                # We search for the specific sender Facebook uses for security codes
                status, messages = mail.search(None, '(FROM "security@facebookmail.com")')
                
                if status == 'OK':
                    mail_ids = messages[0].split()
                    if mail_ids:
                        # Get the latest email ID
                        latest_id = mail_ids[-1]
                        status, data = mail.fetch(latest_id, '(RFC822)')
                        
                        if status == 'OK':
                            raw_email = data[0][1]
                            msg = email.message_from_bytes(raw_email)
                            
                            # Extract subject and body
                            subject = str(msg.get("Subject", ""))
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode()
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode()

                            # 3. Look for the code in subject or body
                            # Facebook codes are usually 6 or 8 digits
                            # Strategy: look for common phrases like "is your Facebook security code"
                            combined_text = f"{subject} {body}"
                            
                            # Pattern 1: Subject usually looks like "123456 is your Facebook security code"
                            match = re.search(r'(\d{6,8})\s+is\s+your\s+Facebook', combined_text, re.IGNORECASE)
                            if match:
                                code = match.group(1)
                                logging.info(f"found_facebook_otp_in_subject_or_body code={code}")
                                mail.logout()
                                return code
                            
                            # Pattern 2: Just find any 6-8 digit number that looks isolated
                            # (Careful with false positives like timestamps)
                            codes = re.findall(r'\b\d{6,8}\b', combined_text)
                            if codes:
                                # Usually the code is prominently displayed
                                code = codes[0]
                                logging.info(f"found_potential_otp code={code}")
                                mail.logout()
                                return code

                mail.logout()
            except Exception as e:
                logging.error(f"gmail_poll_error error={str(e)}")
            
            # Wait before next poll
            time.sleep(10)
            
        logging.warning("otp_polling_timed_out")
        return None

    @staticmethod
    def get_nextdoor_otp(email_user: str, app_password: str, timeout: int = 120) -> Optional[str]:
        """
        Polls Gmail for the latest Nextdoor verification code.
        """
        logging.info(f"polling_gmail_for_nextdoor_otp user={email_user}")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(email_user, app_password)
                mail.select("inbox")
                
                # Nextdoor OTPs usually come from help@nextdoor.com
                status, messages = mail.search(None, '(FROM "help@nextdoor.com")')
                
                if status == 'OK':
                    mail_ids = messages[0].split()
                    if mail_ids:
                        latest_id = mail_ids[-1]
                        status, data = mail.fetch(latest_id, '(RFC822)')
                        
                        if status == 'OK':
                            raw_email = data[0][1]
                            msg = email.message_from_bytes(raw_email)
                            subject = str(msg.get("Subject", ""))
                            
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode()
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode()

                            combined_text = f"{subject} {body}"
                            
                            # Nextdoor codes are typically 6 digits
                            match = re.search(r'\b(\d{6})\b', combined_text)
                            if match:
                                code = match.group(1)
                                logging.info(f"found_nextdoor_otp code={code}")
                                mail.logout()
                                return code

                mail.logout()
            except Exception as e:
                logging.error(f"gmail_poll_error_nextdoor error={str(e)}")
            
            time.sleep(10)
            
        logging.warning("nextdoor_otp_polling_timed_out")
        return None
