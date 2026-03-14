import sys
import os
import json
import yaml
import email.utils
from datetime import datetime, timedelta, timezone


def _date_str_from_publish_date(publish_date: str) -> str:
    if not publish_date:
        return ""
    s = str(publish_date).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt:
            bj = dt.astimezone(timezone(timedelta(hours=8)))
            return bj.date().isoformat()
    except Exception:
        pass
    return ""


def _parse_to_datetime_utc(publish_date: str) -> datetime:
    if not publish_date:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = str(publish_date).strip()
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt:
            return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"]:
            try:
                local_dt = datetime.strptime(s[:19], fmt)
                return local_dt.replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)
            except Exception:
                continue
    except Exception:
        pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_config(path: str, config: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)


def _upsert_subscription(config: dict, sub: dict) -> None:
    subs = config.get("subscriptions", []) or []
    existing_idx = None
    for i, s in enumerate(subs):
        if not isinstance(s, dict):
            continue
        if s.get("platform") == sub.get("platform") and s.get("url") == sub.get("url"):
            existing_idx = i
            break
        if s.get("name") == sub.get("name") and s.get("platform") == sub.get("platform"):
            existing_idx = i
            break
    if existing_idx is None:
        subs.append(sub)
    else:
        subs[existing_idx] = {**subs[existing_idx], **sub}
    config["subscriptions"] = subs


def main():
    raw = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    payload = json.loads(raw) if raw else {}

    platform = payload.get("platform")
    name = payload.get("name")
    url = payload.get("url")
    category = payload.get("category", "General")
    backfill_days = int(payload.get("backfill_days", 90))

    if not platform or not name or not url:
        sys.stderr.write("Missing platform/name/url\n")
        sys.exit(1)

    config_path = payload.get("config_path") or "config.yaml"
    config = _load_config(config_path)
    _upsert_subscription(config, {"platform": platform, "name": name, "url": url, "category": category})
    _save_config(config_path, config)

    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    from src.fetchers.factory import FetcherFactory
    from src.database import DatabaseManager
    from src.summarizer.llm_summarizer import OpenAISummarizer
    from src.archiver.file_archiver import FileArchiver

    summarizer_config = config.get("summarizer", {}) or {}
    api_key = summarizer_config.get("api_key", "YOUR_API_KEY")
    base_url = summarizer_config.get("base_url")
    model = summarizer_config.get("model", "gpt-3.5-turbo")
    provider = summarizer_config.get("provider", "openai")
    summarizer = OpenAISummarizer(api_key=api_key, base_url=base_url, model=model, provider=provider)

    output_dir = (config.get("output", {}) or {}).get("directory", "archives")
    archiver = FileArchiver(output_dir=output_dir)
    db = DatabaseManager()

    if platform == "douyin":
        # Temporary increase fetch limit for backfill
        # But we only need enough to cover the "limit_count" requirement
        os.environ["DOUYIN_FETCH_LIMIT"] = "50" 

    fetcher = FetcherFactory.get_fetcher(platform)
    items = fetcher.fetch(url)

    # Filter logic:
    # 1. Sort by date desc (assuming fetcher returns somewhat sorted, but let's ensure)
    # 2. Take top N (e.g. 20)
    # 3. Still respect backfill_days cutoff if provided, but count limit is primary now.
    
    # Sort items by date desc
    items.sort(key=lambda x: _parse_to_datetime_utc(x.get("publish_date", "")), reverse=True)
    
    # Limit to top 20
    limit_count = 20
    items = items[:limit_count]

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=backfill_days)

    imported = []
    for item in items:
        pd_str = item.get("publish_date", "")
        dt = _parse_to_datetime_utc(pd_str)
        # Still respect time cutoff if valid date found
        if dt != datetime.min.replace(tzinfo=timezone.utc) and dt < cutoff:
            continue

        item["category"] = category
        existing = db.get_article(item.get("url"))
        summary = existing.get("summary") if existing else ""
        if not summary:
            summary = summarizer.summarize(item.get("content", ""), video_url=item.get("video_url") or None)
        item["summary"] = summary
        db.save_article(item, summary)
        imported.append(item)

    affected_dates = sorted({d for d in (_date_str_from_publish_date(i.get("publish_date", "")) for i in imported) if d})
    for date_str in affected_dates:
        day_items = db.get_articles_by_date(date_str)
        summaries = {x.get("url", ""): x.get("summary", "") for x in day_items if x.get("url")}
        archiver.generate_report_for_date(date_str, day_items, summaries)

    result = {
        "subscription": {"platform": platform, "name": name, "url": url, "category": category},
        "fetched": len(items),
        "imported": len(imported),
        "affected_dates": affected_dates,
    }
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout = real_stdout
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
