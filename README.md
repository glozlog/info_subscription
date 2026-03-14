# Information Subscription Aggregator (信息订阅汇总程序)

This project is a modular system designed to aggregate and subscribe to information updates from various social media platforms (WeChat Official Accounts, Douyin, Bilibili, etc.). It runs daily, summarizes content using AI, and archives the results.

## Architecture Overview

The system is designed with a plugin-based architecture to easily support new platforms and summarization methods.

### Core Components

1.  **Fetcher (抓取器)**: Responsible for retrieving content from specific platforms.
    *   `src/fetchers/base.py`: Defines the interface.
    *   Implementations: `Wechat2RssFetcher`, `DouyinFetcher`, `BilibiliFetcher`, `RssFetcher`.
2.  **Summarizer (摘要器)**: Uses AI (LLM) to summarize content.
    *   `src/summarizer/base.py`: Defines the interface.
    *   Implementations: `OpenAISummarizer`, `LocalLLMSummarizer`.
3.  **Archiver (归档器)**: Saves the processed data and generates reports.
    *   `src/archiver/base.py`: Defines the interface.
    *   Implementations: `FileArchiver` (Markdown/JSON).
4.  **Scheduler (调度器)**: Manages the daily execution of tasks.
    *   `src/scheduler/job.py`: Uses `schedule` library.
5.  **Configuration (配置)**: `config.yaml` manages subscriptions and settings.

## Project Structure

```
D:\TRAE\信息订阅\
├── config.yaml           # Configuration file
├── main.py               # Entry point
├── requirements.txt      # Python dependencies
├── src/
│   ├── fetchers/         # Content fetchers
│   │   ├── base.py       # Abstract base class
│   │   └── ...           # Platform implementations
│   ├── summarizer/       # Content summarizers
│   │   ├── base.py       # Abstract base class
│   │   └── ...           # LLM implementations
│   ├── archiver/         # Data storage & reporting
│   │   ├── base.py       # Abstract base class
│   │   └── ...           # Storage implementations
│   ├── scheduler/        # Task scheduling
│   │   └── job.py        # Job management
│   └── utils/            # Helper functions
```

3.  **Implementations**:
    *   `Wechat2RssFetcher`: Fetches WeChat Official Accounts via Wechat2RSS (BID -> RSS).
    *   `RssFetcher`: Generic RSS fetcher.
    *   `BilibiliFetcher`: Fetches latest videos from a UP host.
    *   `DouyinFetcher`: Fetches latest videos from a user profile (uses Playwright).

## Configuration Guide

### 1. WeChat Official Accounts
Due to WeChat's anti-scraping measures, the most stable way to subscribe to updates is by converting them to RSS feeds.

*   **Recommended Tool**: Wechat2RSS (self-hosted)
*   **Configuration**:
    ```yaml
    - platform: wechat2rss
      name: "投资聚义厅"
      url: "3279420503"
    ```

### 2. Bilibili
Find the user's space URL (e.g., `https://space.bilibili.com/123456`).
```yaml
- platform: bilibili
  url: "https://space.bilibili.com/123456"
```

### 3. Douyin
Find the user's profile URL (e.g., `https://www.douyin.com/user/...`).
Note: Douyin fetching is experimental and may break due to anti-bot protection.
```yaml
- platform: douyin
  url: "https://www.douyin.com/user/..."
```

## Adding New Subscriptions (首次引入逻辑)

When a new subscription is added from the console, the program performs an initial backfill:

- Backfill window: last 90 days (about 3 months)
- For all newly imported items: generate AI summaries and write them into the database
- For affected dates: rebuild daily archives (JSON/Markdown/HTML) from the database

This first import is expected to take longer than daily updates.

## Running Tests

To verify your fetchers without waiting for the scheduled job:

```bash
python test_fetchers.py
```

## Extending the System

To add a new platform (e.g., Twitter):
1.  Create a new file in `src/fetchers/twitter.py`.
2.  Inherit from `BaseFetcher`.
3.  Implement `fetch()` and `validate_url()`.
4.  Update the factory logic (to be implemented) to use the new fetcher.
