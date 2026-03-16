"""
日期标准化测试脚本
"""
import sys
import tempfile
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import DateTimeUtil, DatabaseManager


def test_date_standardization():
    """测试日期标准化功能"""
    print("=" * 60)
    print("DateTimeUtil Standardization Tests")
    print("=" * 60)
    
    test_cases = [
        # (输入, 期望输出模式)
        ("2024-01-15 14:30:00", "2024-01-15 14:30:00"),  # 已经是标准格式
        ("2024-01-15", "2024-01-15 00:00:00"),           # 只有日期
        ("2024/01/15 14:30:00", "2024-01-15 14:30:00"),  # 斜杠分隔
        ("2024年1月15日 14:30", "2024-01-15 14:30:00"),  # 中文格式
        ("1月15日", None),                                # 当年日期（动态）
        ("刚刚", None),                                   # 相对时间（动态）
        ("昨天", None),                                   # 相对时间（动态）
        ("3天前", None),                                  # 相对时间（动态）
        ("Mon, 15 Jan 2024 14:30:00 GMT", "2024-01-15 22:30:00"),  # RFC 2822 (GMT+8)
        ("2024-01-15T14:30:00", "2024-01-15 14:30:00"),  # ISO 格式
        (None, None),                                      # None 输入
        ("", None),                                        # 空字符串
        ("invalid date", None),                           # 无效日期
    ]
    
    print("\nTest cases:")
    for input_val, expected in test_cases:
        result = DateTimeUtil.standardize(input_val)
        
        # 对于动态结果，只检查格式
        if expected is None:
            # 检查结果是否为有效的标准格式
            is_valid = len(result) == 19 and result[4] == '-' and result[7] == '-'
            status = "✓" if is_valid else "✗"
            print(f"  {status} {repr(input_val):30} -> {result}")
        else:
            status = "✓" if result == expected else "✗"
            print(f"  {status} {repr(input_val):30} -> {result}")
            if result != expected:
                print(f"      Expected: {expected}")


def test_database_integration():
    """测试数据库集成"""
    print("\n" + "=" * 60)
    print("Database Integration Tests")
    print("=" * 60)
    
    # 使用临时数据库
    temp_db = tempfile.mktemp(suffix='.db')
    db = DatabaseManager(db_path=temp_db)
    
    # 测试数据 - 各种日期格式
    test_items = [
        {
            'url': 'http://test.com/1',
            'title': 'Article 1',
            'content': 'Content 1',
            'author': 'Author 1',
            'platform': 'test',
            'category': 'test',
            'publish_date': '2024-01-15 14:30:00',  # 标准格式
        },
        {
            'url': 'http://test.com/2',
            'title': 'Article 2',
            'content': 'Content 2',
            'author': 'Author 2',
            'platform': 'test',
            'category': 'test',
            'publish_date': '2024/01/15',  # 斜杠格式
        },
        {
            'url': 'http://test.com/3',
            'title': 'Article 3',
            'content': 'Content 3',
            'author': 'Author 3',
            'platform': 'test',
            'category': 'test',
            'publish_date': '2024年1月15日 10:30',  # 中文格式
        },
        {
            'url': 'http://test.com/4',
            'title': 'Article 4',
            'content': 'Content 4',
            'author': 'Author 4',
            'platform': 'test',
            'category': 'test',
            'publish_date': '昨天',  # 相对时间
        },
    ]
    
    print("\n1. Saving articles with various date formats...")
    for item in test_items:
        db.save_article(item)
        print(f"  Saved: {item['url']} with date '{item['publish_date']}'")
    
    print("\n2. Checking standardized dates in database...")
    articles = db.get_all_articles(limit=10)
    for article in articles:
        print(f"  {article['url']}: {article['publish_date']}")
    
    print("\n3. Testing date range query...")
    results = db.get_articles_by_date_range('2024-01-14', '2024-01-16')
    print(f"  Found {len(results)} articles between 2024-01-14 and 2024-01-16")
    
    print("\n4. Testing specific date query...")
    results = db.get_articles_by_date('2024-01-15')
    print(f"  Found {len(results)} articles on 2024-01-15")
    
    # 清理
    os.unlink(temp_db)
    print("\n  Cleaned up temp database")


def test_batch_migration():
    """测试批量日期迁移"""
    print("\n" + "=" * 60)
    print("Batch Date Migration Test")
    print("=" * 60)
    
    # 创建临时数据库
    temp_db = tempfile.mktemp(suffix='.db')
    
    # 使用原始 sqlite3 插入非标准日期数据
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE articles (
            url TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            author TEXT,
            platform TEXT,
            category TEXT,
            publish_date TEXT,
            video_url TEXT,
            summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 插入各种非标准格式的日期
    test_dates = [
        ('http://test.com/1', '2024/01/15 14:30'),
        ('http://test.com/2', '2024年1月15日'),
        ('http://test.com/3', '刚刚'),
        ('http://test.com/4', '昨天'),
        ('http://test.com/5', '2024-01-15'),  # 已经是部分标准
    ]
    
    for url, date in test_dates:
        cursor.execute('''
            INSERT INTO articles (url, title, publish_date)
            VALUES (?, ?, ?)
        ''', (url, 'Test', date))
    
    conn.commit()
    conn.close()
    
    print("\n1. Created database with non-standard dates:")
    for url, date in test_dates:
        print(f"  {url}: {date}")
    
    print("\n2. Initializing DatabaseManager (triggers migration)...")
    db = DatabaseManager(db_path=temp_db)
    
    print("\n3. Checking migrated dates:")
    articles = db.get_all_articles(limit=10)
    for article in articles:
        print(f"  {article['url']}: {article['publish_date']}")
    
    # 验证所有日期都是标准格式
    all_standard = all(
        len(a['publish_date']) == 19 and a['publish_date'][4] == '-'
        for a in articles
    )
    print(f"\n  All dates standardized: {all_standard}")
    
    # 清理
    os.unlink(temp_db)
    print("\n  Cleaned up temp database")


def main():
    """运行所有测试"""
    try:
        test_date_standardization()
    except Exception as e:
        print(f"Date standardization test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_database_integration()
    except Exception as e:
        print(f"Database integration test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_batch_migration()
    except Exception as e:
        print(f"Batch migration test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
