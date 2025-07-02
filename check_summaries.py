import sqlite3

conn = sqlite3.connect('summaries.db')
c = conn.cursor()

c.execute('SELECT COUNT(*) FROM summaries')
total = c.fetchone()[0]
print(f'Total summaries: {total}')

if total > 0:
    c.execute('SELECT uid, subject, from_name FROM summaries ORDER BY uid DESC LIMIT 10')
    print('\nLatest summaries:')
    for row in c.fetchall():
        print(f'  UID {row[0]}: "{row[1]}" from {row[2]}')

conn.close()