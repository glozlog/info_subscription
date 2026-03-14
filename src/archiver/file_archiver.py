import os
import time
import json
from typing import List, Dict, Any
from .base import BaseArchiver
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import email.utils

class FileArchiver(BaseArchiver):
    """
    Archives content to local Markdown, HTML, and JSON files.
    """
    
    def __init__(self, output_dir: str = "archives"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
    def save(self, data: List[Dict[str, Any]], category: str) -> bool:
        """
        Not used directly in this simple implementation.
        """
        return True

    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse date string from various formats into a datetime object.
        Returns a naive datetime object (implicitly UTC) for sorting.
        """
        if not date_str:
            return datetime.min
            
        from datetime import timedelta, timezone
        
        # 1. Try RFC 2822 (RSS format, e.g., "Wed, 18 Feb 2026 01:00:00 GMT")
        try:
            dt = email.utils.parsedate_to_datetime(date_str)
            if dt:
                # Convert to UTC and strip timezone to make it naive
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except:
            pass
            
        # 2. Try ISO-like formats (e.g., "2025-12-31 15:03:39")
        # Assuming these are Beijing Time (UTC+8) if no timezone info
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S"
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # Assume Beijing Time (UTC+8) -> Convert to UTC naive
                # Subtract 8 hours
                return dt - timedelta(hours=8)
            except ValueError:
                continue
                
        # 3. Fallback
        return datetime.min

    def generate_report(self, data: List[Dict[str, Any]], summaries: Dict[str, str]) -> str:
        """
        Generate Markdown, HTML, and JSON reports for the day's content.
        
        Args:
            data: List of all content items fetched today.
            summaries: Dictionary mapping URL to summary text.
        """
        today = time.strftime('%Y-%m-%d')
        
        # 1. Prepare data structure for report
        report_items = []
        for item in data:
            url = item.get('url')
            summary = summaries.get(url, "No summary available.")
            item['summary'] = summary
            report_items.append(item)
            
        # 2. Sort items by date (Newest first)
        report_items.sort(key=lambda x: self._parse_date(x.get('publish_date', '')), reverse=True)
            
        # 3. Generate JSON Report (For Web App)
        json_filename = os.path.join(self.output_dir, f"daily_report_{today}.json")
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(report_items, f, ensure_ascii=False, indent=2)
        print(f"JSON data saved to {json_filename}")
            
        # 3. Generate Markdown Report
        md_filename = os.path.join(self.output_dir, f"daily_report_{today}.md")
        md_content = self._generate_markdown(report_items, today)
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"Markdown report saved to {md_filename}")

        # 4. Generate HTML Report
        html_filename = os.path.join(self.output_dir, f"daily_report_{today}.html")
        self._generate_html(report_items, today, html_filename)
        print(f"HTML report saved to {html_filename}")
        
        return md_content

    def generate_report_for_date(self, date_str: str, data: List[Dict[str, Any]], summaries: Dict[str, str]) -> str:
        report_items = []
        for item in data:
            url = item.get('url')
            summary = summaries.get(url, "No summary available.")
            item['summary'] = summary
            report_items.append(item)

        report_items.sort(key=lambda x: self._parse_date(x.get('publish_date', '')), reverse=True)

        json_filename = os.path.join(self.output_dir, f"daily_report_{date_str}.json")
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(report_items, f, ensure_ascii=False, indent=2)

        md_filename = os.path.join(self.output_dir, f"daily_report_{date_str}.md")
        md_content = self._generate_markdown(report_items, date_str)
        with open(md_filename, 'w', encoding='utf-8') as f:
            f.write(md_content)

        html_filename = os.path.join(self.output_dir, f"daily_report_{date_str}.html")
        self._generate_html(report_items, date_str, html_filename)

        return md_content

    def _generate_markdown(self, items, date_str):
        lines = [f"# Daily Information Summary - {date_str}\n"]
        if not items:
            lines.append("No updates found today.")
        
        for item in items:
            lines.append(f"## [{item.get('title')}]({item.get('url')})")
            lines.append(f"- **Platform**: {item.get('platform')}")
            lines.append(f"- **Author**: {item.get('author')}")
            lines.append(f"- **Date**: {item.get('publish_date')}")
            lines.append(f"\n**Summary**:\n{item.get('summary')}\n")
            lines.append("---\n")
        return "\n".join(lines)

    def _generate_html(self, items, date_str, output_path):
        try:
            # Assuming templates are in src/templates
            template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template('report.html')
            
            html_content = template.render(date=date_str, items=items)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except Exception as e:
            print(f"Error generating HTML report: {e}")
