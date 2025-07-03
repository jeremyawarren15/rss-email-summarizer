import os
import logging
from flask import Flask, Response, jsonify, request
from dotenv import load_dotenv
from email_fetcher import fetch_emails_since, get_latest_uid
from summarizer import summarize_email
from persistence import init_db, insert_summary, fetch_all_summaries, get_db_path
from feedgen.feed import FeedGenerator
from apscheduler.schedulers.background import BackgroundScheduler
from imapclient import IMAPClient
import requests
import sqlite3
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
LAST_UID_FILE = 'last_uid.txt'  # Simplified - just use current directory


def read_last_uid():
    if os.path.exists(LAST_UID_FILE):
        with open(LAST_UID_FILE, 'r') as f:
            try:
                uid = int(f.read().strip())
                logger.info(f'Read last UID from file: {uid}')
                return uid
            except Exception as e:
                logger.error(f'Failed to read last UID from file: {e}')
                return None
    logger.info('No last_uid.txt file found')
    return None

def write_last_uid(uid):
    # Debug information
    logger.info(f'Attempting to write UID {uid} to {LAST_UID_FILE}')

    # Get user info (Unix/Linux only)
    try:
        logger.info(f'Current user ID: {os.getuid()}')
    except AttributeError:
        logger.info('Running on Windows (no getuid available)')

    logger.info(f'Current working directory: {os.getcwd()}')
    logger.info(f'Directory writable: {os.access(".", os.W_OK)}')

    if os.path.exists(LAST_UID_FILE):
        logger.info(f'File exists, writable: {os.access(LAST_UID_FILE, os.W_OK)}')
    else:
        logger.info('File does not exist, will create new')

    try:
        with open(LAST_UID_FILE, 'w') as f:
            f.write(str(uid))
        logger.info(f'Successfully updated last UID to {uid}')
    except Exception as e:
        logger.error(f'Failed to write UID file: {e}')
        raise e


def initialize_last_uid():
    if not os.path.exists(LAST_UID_FILE) or open(LAST_UID_FILE).read().strip() in ('', '0'):
        logger.info('Initializing last_uid.txt with the highest UID in the mailbox...')
        latest_uid = get_latest_uid()
        if latest_uid:
            write_last_uid(latest_uid)
            logger.info(f'last_uid.txt initialized to {latest_uid}')
        else:
            logger.info('No emails found to initialize last_uid.txt.')


def process_emails():
    logger.info('Starting email processing...')
    last_uid = read_last_uid()
    logger.info(f'Last processed UID: {last_uid}')
    try:
        emails = fetch_emails_since(last_uid)
        logger.info(f'Fetched {len(emails)} new emails.')
        if emails:
            logger.info(f'Email UIDs to process: {[email["uid"] for email in emails]}')
    except Exception as e:
        logger.error(f'Error fetching emails: {e}')
        return
    max_uid = last_uid or 0
    for email in emails:
        uid = email['uid']
        subject = email['subject']
        from_name = email['from_name']
        date = email['date']
        body = email['body']
        logger.info(f'Processing email UID {uid}: {subject}')
        try:
            result = summarize_email(subject, from_name, date, body)
            logger.info(f'Summarizer result for UID {uid}: {result}')
            if result['is_important']:
                insert_summary(uid, subject, from_name, date, result['summary'], result.get('ai_summary'))
                logger.info(f'Stored summary for UID {uid}')
            else:
                logger.info(f'Email UID {uid} not important, skipping.')
        except Exception as e:
            logger.error(f'Error summarizing/storing email UID {uid}: {e}')
        if uid > max_uid:
            max_uid = uid
    if max_uid != (last_uid or 0):
        logger.info(f'Updating last UID from {last_uid} to {max_uid}')
        write_last_uid(max_uid)
    else:
        logger.info(f'No new emails processed, keeping last UID at {last_uid}')
    logger.info('Email processing complete.')


def parse_summary_text(raw_summary):
    """
    Parse the structured summary format and extract just the summary text.
    Expected format:
    Subject: [subject]
    From: [sender]
    Summary: [summary text]
    """
    if not raw_summary:
        return raw_summary

    lines = raw_summary.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('Summary:'):
            # Extract everything after "Summary:"
            return line[8:].strip()  # Remove "Summary:" prefix

    # Fallback: if no "Summary:" line found, return the last non-empty line
    # or the whole text if it's short
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    if non_empty_lines:
        if len(raw_summary) < 200:
            return raw_summary  # Short text, return as-is
        else:
            return non_empty_lines[-1]  # Return last line

    return raw_summary


def get_last_n_day_summaries(n=30):
    all_summaries = fetch_all_summaries()
    # Group summaries by date
    grouped = defaultdict(list)
    for summary in all_summaries:
        # Parse the date string to a datetime object
        try:
            email_date = datetime.strptime(summary['date'][:25], '%a, %d %b %Y %H:%M:%S')
        except Exception:
            try:
                email_date = datetime.strptime(summary['date'][:19], '%Y-%m-%d %H:%M:%S')
            except Exception:
                continue
        # Handle both old (from_addr) and new (from_name) database records
        from_name = summary.get('from_name') or summary.get('from_addr', 'Unknown')

        # Use clean ai_summary if available, otherwise parse the old structured summary
        clean_summary = summary.get('ai_summary')
        if not clean_summary:
            clean_summary = parse_summary_text(summary['summary'])

        grouped[email_date.date()].append({
            'subject': summary['subject'],
            'from_name': from_name,
            'summary': clean_summary,
            'time': email_date.strftime('%I:%M %p').lstrip('0'),
        })
    # Sort by date descending and take the last n days
    sorted_days = sorted(grouped.keys(), reverse=True)[:n]
    return [(day, grouped[day]) for day in sorted_days]


@app.route('/rss')
def rss_feed():
    fg = FeedGenerator()
    fg.title('Important Emails Digest')
    fg.link(href='http://localhost:5000/rss', rel='self')
    fg.description('Daily digests of important emails as determined by AI')
    fg.language('en')

    digests = get_last_n_day_summaries(30)
    for day, summaries in digests:
        if not summaries:
            continue
        title_date = day.strftime('%B %d, %Y')
        digest = ''
        for i, s in enumerate(summaries):
            if i > 0:
                digest += '<hr style="margin: 20px 0; border: 1px solid #ccc;">'
            digest += f'<div style="margin-bottom: 20px;">'
            digest += f'<h3 style="margin: 0 0 5px 0; color: #333;">{s["subject"]} <span style="font-size: 0.8em; color: #666;">({s["time"]})</span></h3>'
            digest += f'<p style="margin: 5px 0; color: #666; font-style: italic;">From: {s["from_name"]}</p>'
            digest += f'<p style="margin: 10px 0; line-height: 1.4;">{s["summary"]}</p>'
            digest += '</div>'
        fe = fg.add_entry()
        fe.id(f'digest-{day}')
        fe.title(f'Important Emails - {title_date}')
        fe.description(digest)
        fe.pubDate(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc))

    rss_content = fg.rss_str(pretty=True)
    return Response(rss_content, mimetype='application/rss+xml')


@app.route('/status')
def status_check():
    # Check if we should do a full LLM test (add ?test_llm=true to URL)
    test_llm = request.args.get('test_llm', 'false').lower() == 'true'

    status = {'imap': 'ok', 'ollama': 'ok', 'sqlite': 'ok', 'overall': 'ok'}

    # IMAP: check and count emails, list folders
    try:
        logger.info('Checking IMAP connection...')
        with IMAPClient(os.getenv('IMAP_HOST'), port=int(os.getenv('IMAP_PORT', 993)), ssl=True) as server:
            server.login(os.getenv('IMAP_USER'), os.getenv('IMAP_PASSWORD'))
            folders = server.list_folders()
            server.select_folder('INBOX')
            messages = server.search(['ALL'])
            status['imap'] = {
                'status': 'ok',
                'email_count': len(messages),
                'folders': [f[2] for f in folders]
            }
            logger.info(f'IMAP connection OK. Email count: {len(messages)}. Folders: {[f[2] for f in folders]}')
    except Exception as e:
        status['imap'] = {'status': f'error: {e}', 'email_count': None, 'folders': None}
        status['overall'] = 'error'
        logger.error(f'IMAP check failed: {e}')

    # Ollama: lightweight check or full test
    try:
        logger.info('Checking Ollama connection...')
        ollama_url = os.getenv('OLLAMA_API_URL')
        ollama_model = os.getenv('OLLAMA_MODEL', 'llama3')
        ollama_timeout = int(os.getenv('OLLAMA_TIMEOUT', '60'))

        if test_llm:
            # Full test with LLM call
            test_prompt = "Test"
            resp = requests.post(ollama_url, json={"model": ollama_model, "prompt": test_prompt, "stream": False}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            status['ollama'] = {'status': 'ok', 'test_response': data.get('response', '').strip()[:100]}
            logger.info('Ollama LLM test OK.')
        else:
            # Lightweight check - just verify the API endpoint responds
            resp = requests.get(ollama_url.replace('/api/generate', '/'), timeout=5)
            if resp.status_code in [200, 404]:  # 404 is normal for Ollama root
                status['ollama'] = {'status': 'ok', 'note': 'Lightweight check - add ?test_llm=true for full test'}
                logger.info('Ollama connection OK (lightweight check).')
            else:
                raise Exception(f"Unexpected status code: {resp.status_code}")
    except Exception as e:
        status['ollama'] = {'status': f'error: {e}', 'test_response': None}
        status['overall'] = 'error'
        logger.error(f'Ollama check failed: {e}')

    # SQLite: count summaries
    try:
        logger.info('Checking SQLite connection...')
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM summaries')
        count = c.fetchone()[0]
        conn.close()
        status['sqlite'] = {'status': 'ok', 'summary_count': count}
        logger.info(f'SQLite connection OK. Summary count: {count}')
    except Exception as e:
        status['sqlite'] = {'status': f'error: {e}', 'summary_count': None}
        status['overall'] = 'error'
        logger.error(f'SQLite check failed: {e}')

    return jsonify(status)


def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run process_emails every day at 6am server time
    scheduler.add_job(process_emails, 'cron', hour=6, minute=0, id='email_job', replace_existing=True)
    scheduler.start()
    logger.info('Background scheduler started. Email job scheduled for 6am daily.')


if __name__ == '__main__':
    logger.info('Starting app...')
    # Initialize the database
    init_db()
    logger.info('Database initialized.')
    # Initialize last_uid.txt if needed
    initialize_last_uid()
    # Process new emails and store summaries on startup
    process_emails()
    # Start the background scheduler
    start_scheduler()
    # Start the web server
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    logger.info(f'Web server starting on {host}:{port}')
    app.run(host=host, port=port)