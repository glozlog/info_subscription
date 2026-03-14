import sqlite3
import json

def inspect_db_content():
    try:
        conn = sqlite3.connect("data.db")
        cursor = conn.cursor()
        
        # 查找标题包含 "周度复盘" 的文章
        cursor.execute("SELECT url, title, content FROM articles WHERE title LIKE '%周度复盘%'")
        rows = cursor.fetchall()
        
        if not rows:
            print("No articles found matching '周度复盘'.")
            # Try listing all titles
            cursor.execute("SELECT title FROM articles LIMIT 5")
            print("Some available titles:", [r[0] for r in cursor.fetchall()])
            return

        for row in rows:
            url, title, content = row
            print(f"\n--- Article: {title} ---")
            print(f"URL: {url}")
            print(f"Content Length: {len(content) if content else 0}")
            if content:
                print(f"Content Preview (First 200 chars): {content[:200]}")
            else:
                print("Content is EMPTY or NONE.")
                
    except Exception as e:
        print(f"Error inspecting DB: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    inspect_db_content()
