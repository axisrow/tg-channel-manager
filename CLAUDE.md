# CLAUDE.md — tg-channel-manager

Config-driven content pipeline for Telegram channels (OpenClaw skill).
Scout finds news via SearXNG, drafts posts into a queue, a human approves them, Publisher sends to Telegram on a cron schedule. Zero hardcoding — all channel specifics live in config.

## Architecture

```
SearXNG ─curl─► Scout (cron) ─dedup─► content-queue.md (draft)
                                            │
                                       Human review
                                            │
                                       (status → pending)
                                            │
               Telegram ◄── Publisher (cron) ┘
                                │
                          dedup-check.py --add → content-index.json
```

- **Scout** — searches SearXNG, dedup-checks, writes drafts. Falls back to `config.evergreen` topics when no fresh news found.
- **Publisher** — picks one `pending` post per run, alternates rubrics, publishes via `message tool`, removes from queue, registers in dedup index.
- **Human** — changes `draft` → `pending` in `content-queue.md`.

## File Roles

| File | Location | Purpose |
|------|----------|---------|
| `SKILL.md` | skill dir | Runtime reference for the agent: config schema, queue format, rules |
| `scripts/dedup-check.py` | skill dir | Dedup tool (Python 3 stdlib only) |
| `scripts/tgcm.py` | skill dir | Multi-channel management CLI |
| `references/scout-prompt.md` | skill dir | Cron prompt for Scout runs |
| `references/publisher-prompt.md` | skill dir | Cron prompt for Publisher runs |
| `references/cron-setup.md` | skill dir | `openclaw cron add` templates |
| `content-queue.md` | agent workspace | Post queue (draft/pending entries) — gitignored |
| `content-index.json` | agent workspace | Dedup index (`{msgId, topic, links, keywords}[]`) — gitignored |
| `content-perf.log` | agent workspace | Timing log from dedup-check.py — gitignored |

## Configuration

Lives in `openclaw.json` → `skills.entries["tg-channel-manager"].config`.
Full schema is in SKILL.md — don't duplicate it here.

Env var: `SEARXNG_URL` — base URL of SearXNG instance (required).

## dedup-check.py — 3 Modes

```bash
# Check — before drafting (mandatory)
python3 scripts/dedup-check.py --base-dir {workspace} --topic "topic" --links "url1" "url2"

# Add — after publishing
python3 scripts/dedup-check.py --base-dir {workspace} --add <msgId> --topic "topic" --links "url"

# Rebuild — prints manual instructions (Bot API can't read full history)
python3 scripts/dedup-check.py --base-dir {workspace} --rebuild --channel-id "-100xxx"
```

**Dedup algorithm:** extracts words 4+ chars (Unicode regex `[^\W\d_]{4,}`), removes stopwords, compares exact + stem (first 5 chars) overlap. Threshold: score >= 0.4 AND >= 2 matching terms. URLs are normalized (strip protocol, www, trailing slash) for exact match.

## Cron Setup

```bash
openclaw cron add --name "content-scout-1" --schedule "<time>" --timezone "<tz>" \
  --prompt-file "{baseDir}/references/scout-prompt.md"

openclaw cron add --name "content-pub-1" --schedule "<time>" --timezone "<tz>" \
  --prompt-file "{baseDir}/references/publisher-prompt.md"
```

Manage: `openclaw cron list | remove --name <name> | status`

## Multi-Channel Management

CLI: `scripts/tgcm.py` — manages per-channel directories under `{workspace}/tgcm/`.

```bash
# Look up channel-id by username
python3 scripts/tgcm.py --bot-token $TOKEN get-id @username

# Initialize a channel
python3 scripts/tgcm.py --workspace <workspace> init <name>

# List channels
python3 scripts/tgcm.py --workspace <workspace> list

# Bind to Telegram
python3 scripts/tgcm.py --workspace <workspace> bind <name> --channel-id <id>

# Channel info (local + optional Telegram API data)
python3 scripts/tgcm.py --workspace <workspace> --bot-token $TOKEN info <name> --all

# Save settings locally (for sandbox environments)
python3 scripts/tgcm.py --workspace <workspace> config set bot-token <token>
python3 scripts/tgcm.py --workspace <workspace> config set searxng-url <url>

# Handle #tgcm connect event
python3 scripts/tgcm.py --workspace <workspace> --dm-chat-id <id> connect --channel-id <id>
```

**Directory structure:**

```
{workspace}/tgcm/
    channels.json        → [{"name", "channelId", "status", "createdAt"}, ...] (auto-generated index)
    {name}/
        channel.json         → per-channel metadata (source of truth)
        content-index.json   → {"version": 1, "posts": [...]}
        content-queue.md     → post queue
```

`channels.json` is auto-rebuilt by `tgcm.py` after `init` and `bind`. To list channels: `tgcm.py list`.

`dedup-check.py` works with per-channel dirs via `--base-dir {workspace}/tgcm/{name}`.

## Key Patterns

- **Queue-based workflow** — all content passes through `content-queue.md`; Scout writes, human approves, Publisher consumes and removes.
- **Mandatory dedup** — Scout MUST run dedup-check.py before every draft; Publisher registers after every publish.
- **Rubric rotation** — Publisher checks last published rubric, prefers a different one from pending posts.
- **Evergreen fallback** — no fresh news → Scout picks from `config.evergreen` list, writes an article-style post with `articleFooter`.
- **Daily cap** — Publisher checks today's published count via `message tool action=search` against `config.maxPostsPerDay`.

## Dependencies

Python 3 (stdlib only), curl, SearXNG instance, openclaw CLI.
