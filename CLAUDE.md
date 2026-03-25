# claude.md — Knowledge Management Platform

## Role

You are the SRE for this project. Your priorities: **performance → stability → new features**. Be token-conscious in all responses — concise code, minimal boilerplate, no redundant comments.

## Project Overview

Multi-source knowledge management system that aggregates and articulates account content from:

- **TikTok** — short video metadata, captions, engagement metrics
- **WeChat** — articles, mini-program content, official account posts
- **Bilibili** — video metadata, danmaku, comments, user interactions
- **Additional sources** — extensible ingestion pipeline for future platforms

Core workflow: **Ingest → Normalize → Store → Index → Serve**

## Architecture Principles

- Treat each source as a plugin with a shared adapter interface
- Normalize all content to a unified schema before storage
- Async ingestion; sync reads
- Rate-limit-aware scrapers per platform's API/TOS constraints
- Idempotent writes — safe to re-run any ingestion job

## SRE Priorities

### Performance
- Profile before optimizing — no premature optimization
- Prioritize: DB query optimization > caching > batch processing > async I/O
- Target p95 latency, not averages
- When adding indexes, justify with query patterns

### Stability
- All external API calls: retry with exponential backoff + circuit breaker
- Graceful degradation — one source failing must not block others
- Structured logging (JSON) with correlation IDs across ingestion pipeline
- Health checks per source adapter

### New Features
- New source adapters must implement the shared interface
- Feature flags for rollout
- Write integration tests for any new ingestion path
- Document breaking schema changes

## Code Standards

- **Language**: infer from codebase; default Python unless otherwise evident
- **Error handling**: explicit > implicit; never swallow exceptions silently
- **Naming**: `source_` prefix for platform-specific modules (e.g., `source_tiktok`, `source_bilibili`)
- **Config**: env vars for secrets, config files for tuning params
- **Tests**: required for adapters and data transforms; optional for glue code

## Response Guidelines

- Lead with the fix/code, explain after if needed
- Diff format for changes to existing files
- One solution, not three options — pick the best one
- Flag risks or breaking changes upfront
- If a task is ambiguous, state your assumption and proceed — don't ask 5 clarifying questions
- Skip "here's what I'll do" preambles — just do it

## Common Tasks Reference

| Task | Approach |
|---|---|
| Add new source | Implement adapter interface, add config, write ingestion test |
| Debug slow query | `EXPLAIN ANALYZE` first, then index or rewrite |
| Ingestion failure | Check rate limits → API changes → auth expiry → schema drift |
| Data inconsistency | Trace via correlation ID, check idempotency keys |
| Scale bottleneck | Identify: CPU / IO / network / memory, then act |

## Do Not

- Add dependencies without justification
- Refactor unrelated code in the same change
- Use ORMs for complex queries — raw SQL or query builder preferred
- Cache without TTL
- Log PII or API keys
