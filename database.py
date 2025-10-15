import sqlite3
from datetime import datetime
from contextlib import contextmanager
import logging

logger = logging.getLogger("Huggingface daily papers")


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

def check_column_exists(cursor, table_name, column_name):
    """檢查欄位是否存在"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def migrate_if_needed(conn):
    """如果需要，自動執行資料庫遷移"""
    cursor = conn.cursor()

    # 檢查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'")
    if not cursor.fetchone():
        return  # 表不存在，將由 create_table 創建

    # 檢查並新增缺少的欄位
    migrations = [
        ('status', "ALTER TABLE papers ADD COLUMN status TEXT DEFAULT 'completed'"),
        ('error_message', "ALTER TABLE papers ADD COLUMN error_message TEXT"),
        ('retry_count', "ALTER TABLE papers ADD COLUMN retry_count INTEGER DEFAULT 0")
    ]

    for column_name, sql in migrations:
        if not check_column_exists(cursor, 'papers', column_name):
            logger.info(f"Migrating database: adding '{column_name}' column")
            cursor.execute(sql)

    conn.commit()

def create_table(conn):
    migrate_if_needed(conn)  # 先執行遷移
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
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )
    ''')

    # 建立索引以提升查詢效能
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_zulip_topic ON papers(zulip_topic)
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_created_at ON papers(created_at)
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_updated_at ON papers(updated_at)
    ''')

    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_status ON papers(status)
    ''')

    conn.commit()

def insert_paper(conn, paper):
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
    INSERT OR REPLACE INTO papers
    (id, title, summary, link, pdf_link, local_pdf, zulip_topic, status, error_message, retry_count, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM papers WHERE id = ?), ?), ?)
    ''', (
        paper['id'],
        paper['title'],
        paper.get('summary', ''),
        paper.get('link', ''),
        paper.get('pdf_link', ''),
        paper.get('local_pdf', ''),
        paper.get('zulip_topic', ''),
        paper.get('status', 'completed'),  # 預設為 completed（成功處理）
        paper.get('error_message', None),
        paper.get('retry_count', 0),
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

def update_paper_status(conn, paper_id, status, error_message=None):
    """
    更新論文處理狀態

    Args:
        conn: 資料庫連接
        paper_id: 論文 ID
        status: 狀態 (pending/processing/completed/failed)
        error_message: 錯誤訊息（可選）
    """
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    if error_message:
        cursor.execute('''
        UPDATE papers
        SET status = ?, error_message = ?, retry_count = retry_count + 1, updated_at = ?
        WHERE id = ?
        ''', (status, error_message, now, paper_id))
    else:
        cursor.execute('''
        UPDATE papers
        SET status = ?, updated_at = ?
        WHERE id = ?
        ''', (status, now, paper_id))

    conn.commit()

def get_failed_papers(conn, max_retry=3):
    """
    獲取處理失敗且重試次數未超過上限的論文

    Args:
        conn: 資料庫連接
        max_retry: 最大重試次數

    Returns:
        失敗論文列表
    """
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM papers
    WHERE status = 'failed' AND retry_count < ?
    ORDER BY updated_at DESC
    ''', (max_retry,))

    results = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in results]

def get_papers_by_status(conn, status):
    """
    根據狀態獲取論文

    Args:
        conn: 資料庫連接
        status: 論文狀態

    Returns:
        論文列表
    """
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM papers WHERE status = ?', (status,))

    results = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in results]    