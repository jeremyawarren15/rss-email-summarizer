import sqlite3
from typing import List, Dict
import os
import logging

logger = logging.getLogger(__name__)

# Module-level variable for fallback database path
_fallback_db_path = None


def get_db_path():
    """Get the database path dynamically."""
    if _fallback_db_path:
        return _fallback_db_path
    return os.path.join(os.getenv('DATA_DIR', '.'), 'summaries.db')


def ensure_data_dir():
    """Ensure the data directory exists."""
    data_dir = os.getenv('DATA_DIR', '.')
    db_path = get_db_path()
    logger.info(f'DATA_DIR environment variable: {repr(data_dir)}')
    logger.info(f'Computed DB_PATH: {repr(db_path)}')

    if data_dir != '.':
        try:
            os.makedirs(data_dir, exist_ok=True)
            logger.info(f'Created/verified data directory: {data_dir}')

            # Check if directory exists and is writable
            if os.path.exists(data_dir):
                logger.info(f'Data directory exists: {data_dir}')
                if os.access(data_dir, os.W_OK):
                    logger.info(f'Data directory is writable: {data_dir}')
                else:
                    logger.error(f'Data directory is not writable: {data_dir}')
            else:
                logger.error(f'Data directory does not exist after creation: {data_dir}')
        except Exception as e:
            logger.error(f'Failed to create data directory {data_dir}: {e}')
    else:
        logger.info('Using current directory for database')


def init_db():
    """Initialize the SQLite database and create the summaries table if it doesn't exist."""
    global _fallback_db_path

    ensure_data_dir()

    try:
        logger.info(f'Attempting to create database at: {get_db_path()}')
        conn = sqlite3.connect(get_db_path())
    except sqlite3.OperationalError as e:
        logger.error(f'Failed to create database at {get_db_path()}: {e}')

        # Fallback: try creating in current directory
        fallback_path = 'summaries.db'
        logger.info(f'Attempting fallback database creation at: {fallback_path}')
        try:
            conn = sqlite3.connect(fallback_path)
            logger.warning(f'Using fallback database location: {fallback_path}')
            # Update the fallback path for future calls
            _fallback_db_path = fallback_path
        except Exception as e2:
            logger.error(f'Fallback database creation also failed: {e2}')
            raise e  # Re-raise the original error

    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS summaries
                 (uid INTEGER PRIMARY KEY, subject TEXT, from_name TEXT, date TEXT, summary TEXT)''')

    # Add ai_summary column for clean summary text (migration-safe)
    try:
        c.execute('ALTER TABLE summaries ADD COLUMN ai_summary TEXT')
    except sqlite3.OperationalError:
        # Column already exists
        pass

    conn.commit()
    conn.close()


def insert_summary(uid: int, subject: str, from_name: str, date: str, summary: str, ai_summary=None):
    """Insert a summary into the database."""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    # Insert with both old and new summary formats for compatibility
    c.execute('INSERT OR REPLACE INTO summaries (uid, subject, from_name, date, summary, ai_summary) VALUES (?, ?, ?, ?, ?, ?)',
              (uid, subject, from_name, date, summary, ai_summary))
    conn.commit()
    conn.close()


def fetch_all_summaries():
    """Fetch all summaries from the database."""
    with sqlite3.connect(get_db_path()) as conn:
        c = conn.cursor()
        # Try to fetch with ai_summary column, fall back to old schema if needed
        try:
            c.execute('SELECT uid, subject, from_name, date, summary, ai_summary FROM summaries ORDER BY date DESC')
        except sqlite3.OperationalError:
            # Old schema without ai_summary column
            c.execute('SELECT uid, subject, from_name, date, summary FROM summaries ORDER BY date DESC')

        rows = c.fetchall()
        summaries = []
        for row in rows:
            summary_dict = {
                'uid': row[0],
                'subject': row[1],
                'from_name': row[2],
                'date': row[3],
                'summary': row[4],
            }
            # Add ai_summary if available (new schema)
            if len(row) > 5:
                summary_dict['ai_summary'] = row[5]
            summaries.append(summary_dict)

        return summaries