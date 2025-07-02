import sqlite3
from typing import List, Dict
import os

DB_PATH = os.path.join(os.getenv('DATA_DIR', '.'), 'summaries.db')


def init_db():
    """Initialize the SQLite database and create the summaries table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Insert with both old and new summary formats for compatibility
    c.execute('INSERT OR REPLACE INTO summaries (uid, subject, from_name, date, summary, ai_summary) VALUES (?, ?, ?, ?, ?, ?)',
              (uid, subject, from_name, date, summary, ai_summary))
    conn.commit()
    conn.close()


def fetch_all_summaries():
    """Fetch all summaries from the database."""
    with sqlite3.connect(DB_PATH) as conn:
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