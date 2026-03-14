import sqlite3
import json
import glob
import os
from src.database import DatabaseManager

def migrate():
    print("Starting migration from JSON archives to SQLite...")
    db = DatabaseManager()
    
    # Find all daily report JSON files
    json_files = glob.glob("archives/daily_report_*.json")
    print(f"Found {len(json_files)} JSON files.")
    
    count = 0
    for file_path in json_files:
        print(f"Processing {file_path}...")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                items = json.load(f)
                
            for item in items:
                # Ensure keys match what save_article expects
                # We mainly need 'url' and other metadata
                # Note: 'publish_date' format might need checking but DB stores TEXT
                if db.save_article(item, item.get('summary')):
                    count += 1
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            
    print(f"Migration completed. {count} articles imported/updated.")

if __name__ == "__main__":
    migrate()
