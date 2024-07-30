import sqlite3
from datetime import datetime
from contextlib import contextmanager


'''
SQLITE DB Handling
'''

@contextmanager
def create_connection():
    conn = sqlite3.connect('papers.db')
    try:
        yield conn
    finally:
        conn.close()

def create_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS papers (
        id TEXT PRIMARY KEY,
        title TEXT,
        summary TEXT,
        link TEXT,
        pdf_link TEXT,
        local_pdf TEXT,
        zulip_topic TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    ''')
    conn.commit()

def insert_paper(conn, paper):
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
    INSERT OR REPLACE INTO papers 
    (id, title, summary, link, pdf_link, local_pdf, zulip_topic, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM papers WHERE id = ?), ?), ?)
    ''', (
        paper['id'], 
        paper['title'], 
        paper.get('summary', ''),
        paper['link'], 
        paper.get('pdf_link', ''),
        paper.get('local_pdf', ''),
        paper.get('zulip_topic', ''), 
        paper['id'], 
        now, 
        now
    ))
    conn.commit()

def get_paper(conn, paper_id):
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM papers WHERE id = ?', (paper_id,))
    return cursor.fetchone()

def get_all_papers(conn):
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM papers')
    return cursor.fetchall()

def get_paper_by_zulip_topic(conn, zulip_topic):
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM papers WHERE zulip_topic = ?', (zulip_topic,))
    result = cursor.fetchone()
    if result:
        return dict(zip([column[0] for column in cursor.description], result))
    return None    