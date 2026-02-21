---
name: tg-channel-manager
description: |
  Universal config-driven content pipeline engine for any Telegram channel:
  news search via SearXNG, drafts, scheduled publishing, deduplication.
  All channel specifics are defined in config — one skill for any channel.
metadata:
  openclaw:
    emoji: "📡"
    requires:
      bins: ["python3", "curl"]
      env: ["SEARXNG_URL"]
    primaryEnv: "SEARXNG_URL"
---

# TG Channel Manager

Universal content engine for any Telegram channel.
Pipeline: **scout → draft → human approves → publisher**.

All specifics (topics, rubrics, style, filters) are defined in config — the skill contains zero hardcoded values.

## Configuration

Parameters are read from `openclaw.json` → `skills.entries["tg-channel-manager"]`:

### Telegram

| Parameter | Type | Description |
|-----------|------|-------------|
| `config.channelId` | string | Telegram channel ID for publishing |
| `config.chatId` | string | Channel community chat ID (optional) |

### Limits & Schedule

| Parameter | Type | Description |
|-----------|------|-------------|
| `config.maxPostsPerDay` | number | Maximum posts per day |
| `config.maxDraftsPerRun` | number | Maximum drafts per scout run |
| `config.timezone` | string | Schedule timezone (IANA format) |
| `config.language` | string | Post language (ru, en, ...) |
| `config.cronScoutTimes` | string[] | Scout schedules (cron format) |
| `config.cronPublisherTimes` | string[] | Publisher schedules (cron format) |

### Content

| Parameter | Type | Description |
|-----------|------|-------------|
| `config.rubrics` | array | Rubrics: `[{id, emoji, name}, ...]` |
| `config.searchQueries` | string[] | Search queries for SearXNG |
| `config.searchInclude` | string | What to look for (filter description) |
| `config.searchExclude` | string | What to discard (filter description) |
| `config.evergreen` | string[] | Topics for articles when there are no news |

### Post Style

| Parameter | Type | Description |
|-----------|------|-------------|
| `config.postStyle.minChars` | number | Minimum characters per post |
| `config.postStyle.maxChars` | number | Maximum characters per post |
| `config.postStyle.emojiTitle` | boolean | Emoji before the title |
| `config.postStyle.boldTitle` | boolean | Bold title |
| `config.postStyle.signature` | string | Post signature |
| `config.postStyle.newsFooter` | string | Extra text for news posts (empty = none) |
| `config.postStyle.articleFooter` | string | Extra text for articles (empty = none) |

### Environment

| Parameter | Type | Description |
|-----------|------|-------------|
| `env.SEARXNG_URL` | string | SearXNG instance URL |

`{baseDir}` — path to the skill folder (where this file resides).

## Runtime Files

- **`content-queue.md`** — post queue (draft / pending). Located in the agent's workspace, NOT in the skill folder.
- **`content-index.json`** — deduplication index. Located in the agent's workspace.

### Entry Format in content-queue.md

```markdown
### <number>
- **Status:** draft | pending
- **Rubric:** <emoji> <name> (from config.rubrics)
- **Topic:** <topic>
- **Source:** <url> (for news)
- **Text:**

<post text>
```

Statuses:
- **draft** — draft, awaiting approval
- **pending** — approved, ready for publishing

After publishing, the entry is **removed** from content-queue.md.

## Pipeline

### 1. Scout (cron)

Prompt: `{baseDir}/references/scout-prompt.md`

1. Executes search queries from `config.searchQueries` via `$SEARXNG_URL`
2. Filters by `config.searchInclude` / `config.searchExclude`
3. Checks for duplicates via dedup-check.py
4. Writes a draft to content-queue.md with **draft** status
5. Maximum `config.maxDraftsPerRun` drafts per run
6. If no news found — picks a topic from `config.evergreen`

### 2. Approval (human)

Human reviews draft → changes status to **pending**.

### 3. Publisher (cron)

Prompt: `{baseDir}/references/publisher-prompt.md`

1. Reads content-queue.md
2. Takes the first **pending** post
3. Alternates rubrics when possible
4. Appends signature from `config.postStyle.signature`
5. Publishes via `message tool (action=send, channel=telegram, target=<config.channelId>)`
6. Removes the entry from content-queue.md
7. Adds to dedup index
8. Maximum 1 post per run, `config.maxPostsPerDay` per day

## Telegram API

### Check published posts
```
message tool (action=search, channel=telegram, target=<config.channelId>, query="keywords")
```

### Publish a post
```
message tool (action=send, channel=telegram, target=<config.channelId>, text="post text")
```

## Deduplication

**Before every draft** — mandatory check:

```bash
python3 {baseDir}/scripts/dedup-check.py --base-dir <workspace> --topic "topic" --links "url1" "url2"
```

**After publishing** — add to index:

```bash
python3 {baseDir}/scripts/dedup-check.py --base-dir <workspace> --add <msgId> --topic "topic" --links "url"
```

**Rebuild index** (via Telegram search):

```bash
python3 {baseDir}/scripts/dedup-check.py --base-dir <workspace> --rebuild --channel-id <config.channelId>
```

Index is stored in `<workspace>/content-index.json`.

## SearXNG — News Search

For each query from `config.searchQueries`:

```bash
curl '$SEARXNG_URL/search?q=<query>&format=json&time_range=day&language=en'
```

## Post Format

Defined by `config.postStyle` parameters:

- Title: emoji (if `emojiTitle`) + bold (if `boldTitle`)
- Length: from `minChars` to `maxChars` characters
- Language: from `config.language`
- Signature: `config.postStyle.signature`
- For news: link to original source + `newsFooter` (if not empty)
- For articles: `articleFooter` (if not empty)
- Prefer primary sources (specs, GitHub, official blogs) over summaries
- All links https://
- NO personal data

## Rubrics

Rubrics are defined in `config.rubrics`. Each rubric: `{id, emoji, name}`.

Scout picks the appropriate rubric from the list when creating a draft.

## Initial Cron Setup

See `{baseDir}/references/cron-setup.md` — `openclaw cron add` command templates.
