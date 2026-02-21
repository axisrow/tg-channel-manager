# tg-channel-manager

Universal config-driven content pipeline for any Telegram channel. An [OpenClaw](https://openclaw.dev) skill package.

## What it does

One skill, any channel — all specifics (topics, rubrics, style, filters) live in `openclaw.json` config, not in code.

**Pipeline:** Scout (cron) → Draft → Human approval → Publisher (cron) → Telegram channel

- **Scout** searches for news via SearXNG, filters duplicates, writes drafts
- **Human** reviews drafts, approves by changing status to `pending`
- **Publisher** picks pending posts, formats, publishes to Telegram, updates dedup index

## Features

- Config-driven: channel ID, rubrics, post style, schedules — all in config
- Deduplication via keyword matching and link checking
- SearXNG integration for news discovery
- Evergreen content fallback when no fresh news
- Rubric rotation for content variety

## Structure

```
├── SKILL.md                    # Skill documentation & config reference
├── scripts/
│   └── dedup-check.py          # Content deduplication tool
└── references/
    ├── cron-setup.md           # Cron setup templates
    ├── scout-prompt.md         # Scout cron prompt
    └── publisher-prompt.md     # Publisher cron prompt
```

## Requirements

- Python 3
- curl
- SearXNG instance (set `SEARXNG_URL` env var)

## Usage

See [SKILL.md](SKILL.md) for full documentation, configuration reference, and pipeline details.

## License

MIT
