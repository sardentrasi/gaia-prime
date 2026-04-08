"""
Email Connector Module (IMAP/SMTP Only)
Handles fetching and sending emails using standard IMAP and SMTP protocols.
Removes dependency on proprietary Gmail/Outlook APIs.
"""

import os
import base64
import logging
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import smtplib
import ssl
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import imapclient
    IMAP_AVAILABLE = True
except ImportError:
    IMAP_AVAILABLE = False

from .config import EmailAccountConfig

logger = logging.getLogger("EleuthiaEmail")

class EmailHandler:
    """Universal email handler supporting multiple accounts via IMAP/SMTP."""
    
    def __init__(self):
        """Initialize with IMAP/SMTP account support."""
        self.imap_clients = {}       # {account_name: imap_client}
        
        # Load account configurations
        # We now treat ALL accounts as IMAP accounts for the purpose of the connector
        # But we still load them from their respective config methods if they were migrated to .env
        # However, the user instruction was to use IMAP/SMTP for everything.
        # The .env migration consolidated everything into IMAP_ACCOUNTS.
        
        self.imap_accounts = EmailAccountConfig.get_imap_accounts()
        
        # Runtime enable/disable state
        self._disabled_accounts = set()
        
        logger.info(f"📧 EmailHandler initialized: {len(self.imap_accounts)} IMAP accounts")
    
    # ============================================================
    # Account Management
    # ============================================================
    
    def get_all_accounts(self) -> List[Dict]:
        """Get all configured accounts with their status."""
        accounts = []
        for acc in self.imap_accounts:
            accounts.append({**acc, 'protocol': 'imap',
                           'active': acc.get('enabled', True) and acc['name'] not in self._disabled_accounts})
        return accounts
    
    def get_accounts_by_category(self, category: str) -> List[Dict]:
        """Get accounts filtered by category (work/personal)."""
        return [a for a in self.get_all_accounts() if a.get('category') == category]
    
    def enable_account(self, account_name: str) -> bool:
        """Enable a previously disabled account."""
        self._disabled_accounts.discard(account_name)
        logger.info(f"✅ Account enabled: {account_name}")
        return True
    
    def disable_account(self, account_name: str) -> bool:
        """Disable an account at runtime."""
        self._disabled_accounts.add(account_name)
        logger.info(f"⛔ Account disabled: {account_name}")
        return True
    
    def is_account_active(self, account: Dict) -> bool:
        """Check if an account is active (enabled and not runtime-disabled)."""
        return (account.get('enabled', True) and 
                account.get('name') not in self._disabled_accounts)

    def get_default_account(self) -> Optional[Dict]:
        """Get default account for sending new emails (Prefers Work > Personal)."""
        accounts = self.get_all_accounts()
        # Filter active
        active = [a for a in accounts if a['active']]
        if not active:
            return None
            
        # Try work
        work = [a for a in active if a.get('category') == 'work']
        if work:
            return work[0]
            
        return active[0]
    
    # ============================================================
    # IMAP Core Methods
    # ============================================================
    
    def _init_imap_account(self, account: Dict) -> bool:
        """Initialize a single IMAP account."""
        if not IMAP_AVAILABLE:
            logger.warning("IMAP libraries not available")
            return False
        
        name = account['name']
        if name in self.imap_clients:
            return True
        
        try:
            host = account.get('host')
            port = int(account.get('port', 993))
            username = account.get('username')
            password = account.get('password')
            
            if not host or not username or not password:
                logger.error(f"IMAP credentials missing: {name}")
                return False
            
            # Context for SSL
            context = ssl.create_default_context()
            
            client = imapclient.IMAPClient(host, port=port, ssl=True, ssl_context=context)
            client.login(username, password)
            self.imap_clients[name] = client
            logger.info(f"✅ IMAP initialized: {name}")
            return True
            
        except Exception as e:
            logger.error(f"IMAP init failed ({name}): {e}")
            return False
    
    def _fetch_imap_account(self, account: Dict, max_results=10) -> List[Dict]:
        """Fetch unread emails from a single IMAP account."""
        name = account['name']
        if name not in self.imap_clients and not self._init_imap_account(account):
            return []
        
        try:
            client = self.imap_clients[name]
            client.select_folder('INBOX')
            messages = client.search(['UNSEEN'])
            
            emails = []
            # Fetch latest first
            messages = sorted(messages, reverse=True)
            
            for msg_id in messages[:max_results]:
                # Use BODY.PEEK[] to avoid marking as read implicitly (optional, handled by logic)
                fetch_data = client.fetch([msg_id], [b'BODY.PEEK[]', b'ENVELOPE', b'INTERNALDATE'])
                msg_data = fetch_data[msg_id]
                
                email_obj = self._parse_imap_message(msg_data, account, uid=msg_id)
                if email_obj:
                    emails.append(email_obj)
            
            logger.info(f"📬 {name}: {len(emails)} unread emails")
            return emails
            
        except Exception as e:
            logger.error(f"IMAP fetch failed ({name}): {e}")
            # Try to reconnect next time
            self.imap_clients.pop(name, None)
            return []
    
    def _parse_imap_message(self, msg_data, account: Dict, uid: int) -> Optional[Dict]:
        """Parse IMAP raw email to standard format."""
        
        def robust_decode(bytes_data: bytes) -> str:
            """Try multiple encodings."""
            if not bytes_data: return ""
            encodings = ['utf-8', 'iso-8859-1', 'windows-1252']
            for enc in encodings:
                try:
                    return bytes_data.decode(enc)
                except UnicodeDecodeError:
                    continue
            return bytes_data.decode('utf-8', errors='replace')

        try:
            raw_email = msg_data[b'BODY[]']
            msg = email.message_from_bytes(raw_email)
            
            # Decode subject
            subject_parts = decode_header(msg.get('Subject', 'No Subject'))
            subject = ""
            for content, encoding in subject_parts:
                if isinstance(content, bytes):
                    if encoding:
                        try:
                            subject += content.decode(encoding)
                        except (LookupError, UnicodeDecodeError):
                            subject += robust_decode(content)
                    else:
                        subject += robust_decode(content)
                else:
                    subject += str(content)
            
            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            # Check charset
                            charset = part.get_content_charset()
                            if charset:
                                try:
                                    body = payload.decode(charset)
                                except (LookupError, UnicodeDecodeError):
                                    body = robust_decode(payload)
                            else:
                                body = robust_decode(payload)
                        break # Found plain text preference
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset()
                    if charset:
                        try:
                            body = payload.decode(charset)
                        except (LookupError, UnicodeDecodeError):
                            body = robust_decode(payload)
                    else:
                        body = robust_decode(payload)
            
            # Header Info
            from_header = msg.get('From', 'Unknown')
            to_header = msg.get('To', '')
            date_header = msg.get('Date', '')
            message_id = msg.get('Message-ID', str(uid))

            return {
                'id': str(uid),
                'header_id': message_id,
                'thread_id': msg.get('In-Reply-To', ''),
                'account_name': account['name'],
                'account_category': account.get('category', 'work'),
                'protocol': 'imap',
                'from': from_header,
                'to': to_header,
                'subject': str(subject),
                'body': body,
                'timestamp': date_header,
                'source': f"imap:{account['name']}"
            }
        except Exception as e:
            logger.error(f"Failed to parse IMAP message ({account['name']}): {e}")
            return None
    
    # ============================================================
    # Unified Fetch Methods
    # ============================================================
    
    def fetch_all_emails(self, category: str = None, max_results: int = 10) -> List[Dict]:
        """Fetch unread emails from ALL enabled IMAP accounts."""
        all_emails = []
        
        for account in self.imap_accounts:
            if not self.is_account_active(account):
                continue
            if category and account.get('category') != category:
                continue
            
            emails = self._fetch_imap_account(account, max_results)
            all_emails.extend(emails)
            
        logger.info(f"📧 Total fetched: {len(all_emails)} emails")
        return all_emails
    
    def fetch_work_emails(self, max_results: int = 10) -> List[Dict]:
        return self.fetch_all_emails(category='work', max_results=max_results)
    
    def fetch_personal_emails(self, max_results: int = 10) -> List[Dict]:
        return self.fetch_all_emails(category='personal', max_results=max_results)
    
    def get_email_summary(self, emails: List[Dict]) -> Dict:
        """Generate summary statistics."""
        summary = {
            'total': len(emails),
            'by_category': {},
            'by_account': {}
        }
        
        for em in emails:
            cat = em.get('account_category', 'unknown')
            acc = em.get('account_name', 'unknown')
            
            if cat not in summary['by_category']:
                summary['by_category'][cat] = {'total': 0, 'accounts': []}
            summary['by_category'][cat]['total'] += 1
            if acc not in summary['by_category'][cat]['accounts']:
                summary['by_category'][cat]['accounts'].append(acc)
            
            if acc not in summary['by_account']:
                summary['by_account'][acc] = {'total': 0, 'category': cat}
            summary['by_account'][acc]['total'] += 1
        
        return summary
    
    # ============================================================
    # Sending & Replying (SMTP)
    # ============================================================
    
    def _send_smtp_email(self, account: Dict, to_address: str, subject: str, body: str, in_reply_to: str = None, html_body: str = None) -> bool:
        """Send email via SMTP."""
        smtp_server = account.get('smtp_server')
        # Default to 587 (TLS) if not set, but code below handles ssl/tls logic
        smtp_port = int(account.get('smtp_port', 587))
        smtp_user = account.get('smtp_user', account.get('username'))
        smtp_password = account.get('smtp_password', account.get('password'))
        
        if not smtp_server or not smtp_password:
            logger.error(f"Missing SMTP config for account {account.get('name')}")
            return False
            
        try:
            msg = MIMEMultipart("alternative")
            
            # Construct Sender
            sender_name = account.get('display_name', account.get('name'))
            if sender_name:
                msg['From'] = f"{sender_name} <{smtp_user}>"
            else:
                msg['From'] = smtp_user
                
            msg['To'] = to_address
            msg['Subject'] = subject
            
            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
                msg['References'] = in_reply_to
            
            # Attach parts
            part1 = MIMEText(body, 'plain')
            msg.attach(part1)
            
            if html_body:
                part2 = MIMEText(html_body, 'html')
                msg.attach(part2)
            
            context = ssl.create_default_context()
            
            # Auto-detect SSL vs STARTTLS based on port
            logger.info(f"🚀 Connecting to SMTP: {smtp_server}:{smtp_port}")
            
            if smtp_port == 465:
                # SSL Connection (Implicit)
                with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            else:
                # TLS Connection (Explicit - STARTTLS)
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    # server.set_debuglevel(1) # Uncomment for debug
                    server.ehlo()
                    try:
                        server.starttls(context=context)
                        server.ehlo()
                    except Exception as tls_error:
                        logger.warning(f"STARTTLS warning: {tls_error}")
                    
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            
            logger.info(f"✅ SMTP Email sent to {to_address}")
            return True
            
        except Exception as e:
            logger.error(f"❌ SMTP Error ({account.get('name')}): {e}")
            return False

    def send_email(self, to_email: str, subject: str, body: str, account_name: str = None, html_body: str = None) -> bool:
        """Send a new email via SMTP."""
        target_account = None
        
        # 1. Find account
        if account_name:
             for acc in self.imap_accounts:
                 if acc['name'] == account_name:
                     target_account = acc
                     break
        
        # 2. Fallback
        if not target_account:
            target_account = self.get_default_account()
            
        if not target_account:
            logger.error("❌ No active email account available to send.")
            return False
            
        return self._send_smtp_email(target_account, to_email, subject, body, html_body=html_body)

    def reply_to_email(self, message_id: str, thread_id: str, reply_body: str, 
                       account_name: str = None, original_email: Optional[Dict] = None, html_body: str = None) -> bool:
        """Reply to an email via SMTP."""
        
        # 1. Identify Target Account
        target_account = None
        if account_name:
            for acc in self.imap_accounts:
                if acc['name'] == account_name:
                    target_account = acc
                    break
        
        if not target_account:
            # Try to match based on original_email context if possible, otherwise default
            if original_email and original_email.get('account_name'):
                orig_name = original_email.get('account_name')
                for acc in self.imap_accounts:
                    if acc['name'] == orig_name:
                        target_account = acc
                        break
            
        if not target_account:
            target_account = self.get_default_account()
            
        if not target_account:
            logger.error("❌ No account available for reply.")
            return False
            
        # 2. Determine To Address
        # In IMAP parsed objects, 'from' contains the sender's address
        to_address = ""
        if original_email:
            to_address = original_email.get('from', original_email.get('sender', ''))
            
        if not to_address:
            logger.error("Cannot reply: missing recipient address.")
            return False
            
        # 3. Determine Subject
        orig_subject = original_email.get('subject', '') if original_email else ''
        subject = f"Re: {orig_subject}" if not orig_subject.lower().startswith('re:') else orig_subject
        
        return self._send_smtp_email(target_account, to_address, subject, reply_body, in_reply_to=message_id, html_body=html_body)

    def mark_as_read(self, message_id: str, account_name: str) -> bool:
        """Mark email as read (IMAP only)."""
        target_account = None
        for acc in self.imap_accounts:
            if acc['name'] == account_name:
                target_account = acc
                break
        
        if not target_account:
            return False
            
        try:
            name = target_account['name']
            if name not in self.imap_clients:
                self._init_imap_account(target_account)
            
            client = self.imap_clients.get(name)
            if client:
                # message_id here is expected to be the UID
                uid = int(message_id)
                client.select_folder('INBOX')
                client.add_flags([uid], [b'\\Seen'])
                return True
        except Exception as e:
            logger.error(f"Failed to mark as read ({account_name}): {e}")
            return False
        
        return False

    def close_all(self):
        """Close all IMAP connections."""
        for name, client in self.imap_clients.items():
            try:
                client.logout()
                logger.info(f"Closed IMAP: {name}")
            except Exception:
                pass
        self.imap_clients.clear()
