#!/usr/bin/env python
"""
資料庫遷移腳本
將現有的 papers.db 升級到新 schema
"""

import sqlite3
import os
import shutil
from datetime import datetime

def backup_database(db_path):
    """備份資料庫"""
    if os.path.exists(db_path):
        backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(db_path, backup_path)
        print(f"✅ Database backed up to: {backup_path}")
        return backup_path
    return None

def check_column_exists(cursor, table_name, column_name):
    """檢查欄位是否存在"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def migrate_database(db_path='papers.db'):
    """執行資料庫遷移"""
    print(f"🔄 Starting database migration for: {db_path}")

    # 備份資料庫
    backup_path = backup_database(db_path)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 檢查並新增 status 欄位
        if not check_column_exists(cursor, 'papers', 'status'):
            print("📝 Adding 'status' column...")
            cursor.execute("ALTER TABLE papers ADD COLUMN status TEXT DEFAULT 'completed'")
            print("✅ 'status' column added")
        else:
            print("⏭️  'status' column already exists")

        # 檢查並新增 error_message 欄位
        if not check_column_exists(cursor, 'papers', 'error_message'):
            print("📝 Adding 'error_message' column...")
            cursor.execute("ALTER TABLE papers ADD COLUMN error_message TEXT")
            print("✅ 'error_message' column added")
        else:
            print("⏭️  'error_message' column already exists")

        # 檢查並新增 retry_count 欄位
        if not check_column_exists(cursor, 'papers', 'retry_count'):
            print("📝 Adding 'retry_count' column...")
            cursor.execute("ALTER TABLE papers ADD COLUMN retry_count INTEGER DEFAULT 0")
            print("✅ 'retry_count' column added")
        else:
            print("⏭️  'retry_count' column already exists")

        conn.commit()

        # 建立索引
        print("\n📝 Creating indexes...")
        indexes = [
            ('idx_zulip_topic', 'CREATE INDEX IF NOT EXISTS idx_zulip_topic ON papers(zulip_topic)'),
            ('idx_created_at', 'CREATE INDEX IF NOT EXISTS idx_created_at ON papers(created_at)'),
            ('idx_updated_at', 'CREATE INDEX IF NOT EXISTS idx_updated_at ON papers(updated_at)'),
            ('idx_status', 'CREATE INDEX IF NOT EXISTS idx_status ON papers(status)')
        ]

        for index_name, sql in indexes:
            cursor.execute(sql)
            print(f"✅ Index '{index_name}' created")

        conn.commit()

        # 驗證遷移
        print("\n🔍 Verifying migration...")
        cursor.execute("PRAGMA table_info(papers)")
        columns = cursor.fetchall()
        print("\nCurrent schema:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='papers'")
        indexes = cursor.fetchall()
        print("\nIndexes:")
        for idx in indexes:
            print(f"  - {idx[0]}")

        # 統計資料
        cursor.execute("SELECT COUNT(*) FROM papers")
        total = cursor.fetchone()[0]
        print(f"\n📊 Total papers: {total}")

        conn.close()

        print("\n✅ Migration completed successfully!")
        print(f"💾 Backup saved at: {backup_path}")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print(f"💾 Database backup available at: {backup_path}")
        print("You can restore by running:")
        print(f"  cp {backup_path} {db_path}")
        raise

if __name__ == "__main__":
    migrate_database()
