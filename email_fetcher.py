import os
from imapclient import IMAPClient
import email
from email.header import decode_header
from dotenv import load_dotenv
from typing import List, Dict, Optional
from email.utils import parseaddr
import re
import html

load_dotenv()

IMAP_HOST = os.getenv('IMAP_HOST')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASSWORD = os.getenv('IMAP_PASSWORD')


def limit_text_length(text, max_length=2000):
    """
    Limit text length while trying to preserve readability.
    """
    if not text or len(text) <= max_length:
        return text

    # Try to cut at a sentence boundary
    truncated = text[:max_length]
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')

    # Cut at the last sentence or paragraph boundary if reasonable
    cut_point = max(last_period, last_newline)
    if cut_point > max_length * 0.7:  # Only if we don't lose too much content
        return text[:cut_point + 1] + "\n\n[Content truncated for length]"
    else:
        return text[:max_length] + "\n\n[Content truncated for length]"


def strip_html(html_content, max_length=2000):
    """
    Strip HTML tags and decode HTML entities to get clean plain text.
    Also handles heavily formatted content and limits length.
    """
    if not html_content:
        return html_content

    # FIRST: Limit the raw HTML length to prevent massive HTML from overwhelming processing
    # This is important for emails with thousands of lines of styling/formatting
    if len(html_content) > 10000:  # Limit raw HTML to 10k chars before processing
        html_content = html_content[:10000] + "..."

    # Remove script and style elements completely (including content)
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML comments
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)

    # Remove HTML tags using regex
    clean_text = re.sub(r'<[^>]+>', '', html_content)

    # Decode HTML entities (like &amp;, &lt;, etc.)
    clean_text = html.unescape(clean_text)

    # Clean up excessive whitespace and newlines
    clean_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', clean_text)  # Multiple newlines -> double newline
    clean_text = re.sub(r'[ \t]+', ' ', clean_text)  # Multiple spaces/tabs -> single space
    clean_text = re.sub(r'\n[ \t]+', '\n', clean_text)  # Remove spaces at start of lines

    # Remove leading/trailing whitespace
    clean_text = clean_text.strip()

    # SECOND: Limit the final clean text length
    if len(clean_text) > max_length:
        # Try to cut at a sentence boundary
        truncated = clean_text[:max_length]
        last_period = truncated.rfind('.')
        last_newline = truncated.rfind('\n')

        # Cut at the last sentence or paragraph boundary if reasonable
        cut_point = max(last_period, last_newline)
        if cut_point > max_length * 0.7:  # Only if we don't lose too much content
            clean_text = clean_text[:cut_point + 1] + "\n\n[Content truncated for length]"
        else:
            clean_text = clean_text[:max_length] + "\n\n[Content truncated for length]"

    return clean_text


def decode_mime_words(s):
    decoded = decode_header(s)
    return ''.join([
        part.decode(enc or 'utf-8') if isinstance(part, bytes) else part
        for part, enc in decoded
    ])


def fetch_emails_since(last_uid: Optional[int] = None) -> List[Dict]:
    """
    Fetch emails from the IMAP server since the given UID.
    Returns a list of dicts with keys: subject, from_name, from_addr, date, body, uid
    """
    emails = []
    with IMAPClient(IMAP_HOST, port=IMAP_PORT, ssl=True) as server:
        server.login(IMAP_USER, IMAP_PASSWORD)
        server.select_folder('INBOX')
        if last_uid:
            # Fetch emails with UID strictly greater than last_uid
            messages = server.search([u'UID', f'{last_uid + 1}:*'])
            # Filter out any emails with UID <= last_uid (just to be safe)
            messages = [uid for uid in messages if uid > last_uid]
        else:
            # Safety check: if no last_uid, only fetch recent emails (last 100)
            # to prevent processing thousands of old emails
            all_messages = server.search(['ALL'])
            if all_messages:
                # Take only the last 100 emails as a safety measure
                messages = sorted(all_messages)[-100:]
                print(f"DEBUG: No last_uid provided, limiting to last 100 emails: {len(messages)} total")
            else:
                messages = []

        # Log what we're fetching for debugging
        if last_uid:
            print(f"DEBUG: Fetching emails with UID > {last_uid}, found UIDs: {messages}")
        else:
            print(f"DEBUG: Fetching recent emails (safety limit), found {len(messages)} UIDs")

        for uid in messages:
            raw_msg = server.fetch([uid], ['RFC822'])[uid][b'RFC822']
            msg = email.message_from_bytes(raw_msg)

            subject = decode_mime_words(msg.get('Subject', ''))
            from_ = decode_mime_words(msg.get('From', ''))
            date = msg.get('Date', '')
            # Parse sender name and email
            name, email_addr = parseaddr(from_)
            from_name = name if name else email_addr
            # Get body (plain text preferred, but strip HTML if needed)
            body = ''
            if msg.is_multipart():
                # Try to find plain text part first
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain' and not part.get('Content-Disposition'):
                        charset = part.get_content_charset() or 'utf-8'
                        raw_payload = part.get_payload(decode=True)
                        # Limit raw payload size before decoding to prevent memory issues
                        if len(raw_payload) > 50000:  # 50KB limit for raw content
                            raw_payload = raw_payload[:50000]
                        body = raw_payload.decode(charset, errors='replace')
                        break

                # If no plain text found, look for HTML and strip it
                if not body:
                    for part in msg.walk():
                        if part.get_content_type() == 'text/html' and not part.get('Content-Disposition'):
                            charset = part.get_content_charset() or 'utf-8'
                            raw_payload = part.get_payload(decode=True)
                            # Limit raw payload size before decoding to prevent memory issues
                            if len(raw_payload) > 50000:  # 50KB limit for raw content
                                raw_payload = raw_payload[:50000]
                            html_body = raw_payload.decode(charset, errors='replace')
                            body = strip_html(html_body)
                            break
            else:
                charset = msg.get_content_charset() or 'utf-8'
                raw_payload = msg.get_payload(decode=True)
                # Limit raw payload size before decoding to prevent memory issues
                if len(raw_payload) > 50000:  # 50KB limit for raw content
                    raw_payload = raw_payload[:50000]
                raw_body = raw_payload.decode(charset, errors='replace')

                # Check if it's HTML content and strip if needed
                if msg.get_content_type() == 'text/html':
                    body = strip_html(raw_body)
                else:
                    body = raw_body

            # Always limit the final body length to prevent overwhelming the LLM
            body = limit_text_length(body)

            emails.append({
                'uid': uid,
                'subject': subject,
                'from_name': from_name,
                'from_addr': email_addr,
                'date': date,
                'body': body,
            })
    return emails


def get_latest_uid() -> Optional[int]:
    """
    Get the highest UID in the INBOX.
    """
    with IMAPClient(IMAP_HOST, port=IMAP_PORT, ssl=True) as server:
        server.login(IMAP_USER, IMAP_PASSWORD)
        server.select_folder('INBOX')
        messages = server.search(['ALL'])
        if not messages:
            return None
        return max(messages)