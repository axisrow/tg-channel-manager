#!/usr/bin/env python3
"""
Multi-channel management CLI for tg-channel-manager.

Usage:
  tgcm.py [--workspace PATH] init <name>
  tgcm.py [--workspace PATH] list
  tgcm.py [--workspace PATH] bind <name> --channel-id ID
  tgcm.py [--workspace PATH] [--bot-token TOKEN] info <name> [--chat] [--subscribers] [--permissions] [--admins] [--all]
  tgcm.py [--bot-token TOKEN] get-id <@username|ID>
  tgcm.py [--workspace PATH] [--bot-token TOKEN] check
  tgcm.py [--workspace PATH] connect --channel-id ID [--channel-title TITLE]
  tgcm.py [--workspace PATH] [--bot-token TOKEN] fetch-posts <name> [--limit N] [--dry-run]
  tgcm.py [--workspace PATH] config set <key> <value>
  tgcm.py [--workspace PATH] config get <key>
  tgcm.py [--workspace PATH] config list

Bot token resolution order: --bot-token arg → .env → TELEGRAM_BOT_TOKEN env → openclaw.json (auto-search) → tgcm/.config.json.
"""

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CHANNEL_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')

# Minimum length for posts imported from t.me/s/.
# Keep it low so short announcements are still indexed for dedup/style.
MIN_POST_LENGTH = 1
MIN_PAGE_SIZE = 10

CONFIG_KEYS = {
    "bot-token": "botToken",
    "searxng-url": "searxngUrl",
}


def validate_channel_name(name):
    """Validate channel name. Returns error message or None."""
    if not CHANNEL_NAME_RE.match(name):
        return (
            f"Invalid channel name '{name}'. "
            "Must match: ^[a-z0-9][a-z0-9_-]{{0,62}}$"
        )
    return None


def get_tgcm_root(workspace):
    """Return the tgcm root directory path."""
    return os.path.join(os.path.abspath(workspace), "tgcm")


def get_channel_dir(workspace, name):
    """Return the channel directory path."""
    return os.path.join(get_tgcm_root(workspace), name)


def load_channel_meta(channel_dir):
    """Load channel.json from a channel directory."""
    path = os.path.join(channel_dir, "channel.json")
    with open(path, "r") as f:
        return json.load(f)


def save_channel_meta(channel_dir, meta):
    """Save channel.json to a channel directory."""
    path = os.path.join(channel_dir, "channel.json")
    with open(path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def sync_channels_index(workspace):
    """Rebuild tgcm/channels.json from per-channel channel.json files."""
    root = get_tgcm_root(workspace)
    if not os.path.isdir(root):
        return

    channels = []
    for entry in sorted(os.listdir(root)):
        meta_path = os.path.join(root, entry, "channel.json")
        if os.path.isfile(meta_path):
            try:
                meta = load_channel_meta(os.path.join(root, entry))
                channels.append({
                    "name": meta["name"],
                    "channelId": meta.get("channelId"),
                    "status": meta.get("status", "initialized"),
                    "createdAt": meta.get("createdAt", ""),
                })
            except (json.JSONDecodeError, KeyError, OSError) as e:
                print(f"[warn] skipping {entry}: {e}", file=sys.stderr)
                continue

    index_path = os.path.join(root, "channels.json")
    with open(index_path, "w") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


def channel_init(workspace, name):
    """Initialize a new channel directory with starter files."""
    err = validate_channel_name(name)
    if err:
        print(err, file=sys.stderr)
        return 1

    channel_dir = get_channel_dir(workspace, name)
    if os.path.exists(channel_dir):
        print(f"Channel '{name}' already exists", file=sys.stderr)
        return 1

    first_init = not os.path.isdir(get_tgcm_root(workspace))
    os.makedirs(channel_dir, exist_ok=True)

    # Seed channels.json from example template on first init
    if first_init:
        example = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "references", "channels.example.json",
        )
        index_dst = os.path.join(get_tgcm_root(workspace), "channels.json")
        if os.path.isfile(example) and not os.path.exists(index_dst):
            shutil.copy2(example, index_dst)

    # content-index.json (versioned)
    index_path = os.path.join(channel_dir, "content-index.json")
    with open(index_path, "w") as f:
        json.dump({"version": 1, "posts": []}, f, ensure_ascii=False, indent=2)

    # content-queue.md (empty)
    queue_path = os.path.join(channel_dir, "content-queue.md")
    with open(queue_path, "w") as f:
        pass

    # channel.json
    meta = {
        "name": name,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channelId": None,
        "status": "initialized",
    }
    save_channel_meta(channel_dir, meta)
    sync_channels_index(workspace)

    print(f"Channel '{name}' initialized at {channel_dir}")
    return 0


def channel_list(workspace):
    """List all channels."""
    root = get_tgcm_root(workspace)
    if not os.path.isdir(root):
        print("No channels found")
        return 0

    channels = []
    for entry in sorted(os.listdir(root)):
        meta_path = os.path.join(root, entry, "channel.json")
        if os.path.isfile(meta_path):
            try:
                meta = load_channel_meta(os.path.join(root, entry))
                channels.append(meta)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                print(f"[warn] skipping {entry}: {e}", file=sys.stderr)
                continue

    if not channels:
        print("No channels found")
        return 0

    for ch in channels:
        cid = ch.get("channelId") or "-"
        print(
            f"{ch['name']}  status={ch['status']}  "
            f"channel_id={cid}  created={ch['createdAt']}"
        )
    return 0


def channel_bind(workspace, name, channel_id):
    """Bind a channel to a Telegram channel ID."""
    channel_dir = get_channel_dir(workspace, name)
    if not os.path.isdir(channel_dir):
        print(f"Channel '{name}' not found", file=sys.stderr)
        return 1

    try:
        meta = load_channel_meta(channel_dir)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading channel.json: {e}", file=sys.stderr)
        return 1
    if meta.get("channelId") is not None:
        print(
            f"Channel '{name}' is already bound to {meta['channelId']}",
            file=sys.stderr,
        )
        return 1

    meta["channelId"] = channel_id
    meta["status"] = "connected"
    save_channel_meta(channel_dir, meta)
    sync_channels_index(workspace)

    print(f"Channel '{name}' bound to {channel_id}")
    return 0


def tg_api_call(token, method, params=None, json_body=None):
    """Call Telegram Bot API. Returns result dict or None on error."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    if json_body:
        data = json.dumps(json_body).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
        )
    else:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = url
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("ok"):
            return data.get("result")
        desc = data.get("description", "unknown error")
        print(f"Telegram API {method}: {desc}", file=sys.stderr)
        return None
    except urllib.error.HTTPError as e:
        desc = f"HTTP {e.code}"
        try:
            body = json.loads(e.read().decode())
            desc = body.get("description", desc)
        except (json.JSONDecodeError, OSError):
            pass
        print(f"Telegram API {method}: {desc}", file=sys.stderr)
        return None
    except (urllib.error.URLError, OSError) as e:
        print(f"Telegram API {method}: {e}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Telegram API {method}: invalid response: {e}", file=sys.stderr)
        return None


def _split_text(text, limit):
    """Split text at a natural boundary before *limit*.

    Tries (in order): last ``\\n\\n``, last ``\\n``, last space.
    Returns ``(head, tail)`` where ``len(head) <= limit``.

    Avoids leaving an orphaned section header (``# …``) at the end of
    *head* — if the last paragraph of *head* is a header line, the split
    is moved to the previous paragraph break so the header stays with its
    content.
    """
    if len(text) <= limit:
        return text, ""
    # Try paragraph break
    pos = text.rfind("\n\n", 0, limit + 1)
    if pos > 0:
        # Guard against orphaned header at end of head
        head = text[:pos]
        last_nl = head.rfind("\n")
        last_line = head[last_nl + 1:] if last_nl >= 0 else head
        if last_line.lstrip().startswith("#"):
            earlier = text.rfind("\n\n", 0, pos)
            if earlier > 0:
                return text[:earlier], text[earlier + 2:]
        return head, text[pos + 2:]
    # Try newline
    pos = text.rfind("\n", 0, limit + 1)
    if pos > 0:
        return text[:pos], text[pos + 1:]
    # Try space
    pos = text.rfind(" ", 0, limit + 1)
    if pos > 0:
        return text[:pos], text[pos + 1:]
    # Hard cut (shouldn't happen with real text)
    return text[:limit], text[limit:]


SENDPHOTO_CAPTION_LIMIT = 1024
SENDMESSAGE_TEXT_LIMIT = 4096


def publish_post(token, chat_id, text, photo_url=None, parse_mode=None,
                 text_format=None, source_url=None):
    """Publish post to channel. Splits long text with photo into 2 messages.

    text_format: "md" converts markdown to Telegram HTML before sending,
                 None or "plain" sends text as-is.
    source_url: optional URL to append as source link at the end of the post.

    Returns list of Telegram message dicts on success, or None on error.
    """
    convert = text_format == "md"
    if convert:
        parse_mode = "HTML"

    results = []

    if not photo_url:
        # Text-only
        content = md_to_tg_html(text) if convert else text
        content = append_source_link(content, source_url, parse_mode)
        params = {"chat_id": chat_id, "text": content[:SENDMESSAGE_TEXT_LIMIT]}
        if parse_mode:
            params["parse_mode"] = parse_mode
        msg = tg_api_call(token, "sendMessage", json_body=params)
        return [msg] if msg else None

    if len(text) <= SENDPHOTO_CAPTION_LIMIT:
        # Short text — single photo message
        content = md_to_tg_html(text) if convert else text
        content = append_source_link(content, source_url, parse_mode)
        params = {"chat_id": chat_id, "photo": photo_url, "caption": content}
        if parse_mode:
            params["parse_mode"] = parse_mode
        msg = tg_api_call(token, "sendPhoto", json_body=params)
        return [msg] if msg else None

    # Long text with photo — split on raw markdown, then convert each chunk
    head, tail = _split_text(text, SENDPHOTO_CAPTION_LIMIT)
    if convert:
        head = md_to_tg_html(head)
        tail = md_to_tg_html(tail)
    tail = append_source_link(tail, source_url, parse_mode)

    params1 = {"chat_id": chat_id, "photo": photo_url, "caption": head}
    if parse_mode:
        params1["parse_mode"] = parse_mode
    msg1 = tg_api_call(token, "sendPhoto", json_body=params1)
    if not msg1:
        return None
    results.append(msg1)

    params2 = {"chat_id": chat_id, "text": tail}
    if parse_mode:
        params2["parse_mode"] = parse_mode
    msg2 = tg_api_call(token, "sendMessage", json_body=params2)
    if not msg2:
        return None
    results.append(msg2)

    return results


def append_source_link(text, source_url, parse_mode=None):
    """Append source link to the end of post text.

    Called AFTER md_to_tg_html() so the <a> tag is not escaped.
    """
    if not source_url:
        return text
    if parse_mode == "HTML":
        return text + f'\n\n\U0001f517 <a href="{source_url}">Оригинал статьи</a>'
    return text + f"\n\n\U0001f517 Оригинал статьи: {source_url}"


def _find_queue_post(content, post_id):
    """Find post by number in content-queue.md text.

    Returns dict with 'source' and 'status' keys, or None if not found.
    """
    pattern = (
        r'###\s+' + str(post_id) + r'\s*\n'
        r'(?:- \*\*\w+:\*\*.*\n)*?'
    )
    match = re.search(pattern, content)
    if not match:
        return None
    # Extract the metadata block after the ### header
    start = match.start()
    block = content[start:]
    # Find next post header or end of content
    next_post = re.search(r'\n###\s+\d+', block[4:])
    if next_post:
        block = block[:next_post.start() + 4]
    source_match = re.search(r'- \*\*Source:\*\*\s*(.+)', block)
    status_match = re.search(r'- \*\*Status:\*\*\s*(.+)', block)
    return {
        "source": source_match.group(1).strip() if source_match else None,
        "status": status_match.group(1).strip() if status_match else None,
    }


def _update_queue_status(queue_path, post_id, new_status):
    """Update Status of a specific post in content-queue.md file."""
    with open(queue_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Find the post header and its Status line
    pattern = (
        r'(###\s+' + str(post_id) + r'\s*\n'
        r'- \*\*Status:\*\*)\s+\S+'
    )
    new_content, count = re.subn(pattern, r'\1 ' + new_status, content)
    if count == 0:
        return False
    with open(queue_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def _yn(v):
    """Format boolean as 'yes'/'no'."""
    return "yes" if v else "no"


def channel_info(workspace, name, bot_token, flags):
    """Display channel information (local + optional Telegram API data)."""
    channel_dir = get_channel_dir(workspace, name)
    if not os.path.isdir(channel_dir):
        print(f"Channel '{name}' not found", file=sys.stderr)
        return 1

    try:
        meta = load_channel_meta(channel_dir)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading channel metadata: {e}", file=sys.stderr)
        return 1

    # Content index stats
    total_posts = 0
    index_path = os.path.join(channel_dir, "content-index.json")
    try:
        with open(index_path, "r") as f:
            index_data = json.load(f)
        posts = index_data.get("posts", []) if isinstance(index_data, dict) else index_data
        total_posts = len(posts)
    except (json.JSONDecodeError, OSError):
        pass

    # Queue stats
    draft_count, pending_count = 0, 0
    queue_path = os.path.join(channel_dir, "content-queue.md")
    try:
        with open(queue_path, "r") as f:
            content = f.read()
        draft_count = content.count("**Status:** draft")
        pending_count = content.count("**Status:** pending")
    except OSError:
        pass

    # Local block (always)
    print(f"Channel: {meta['name']}")
    print(f"  Status:     {meta['status']}")
    print(f"  Channel ID: {meta.get('channelId') or '(not bound)'}")
    print(f"  Created:    {meta['createdAt']}")
    print(f"  Published:  {total_posts} posts")
    print(f"  Queue:      {draft_count} draft, {pending_count} pending")

    # Check if any Telegram flags requested
    has_tg_flags = any(flags.values())
    if not has_tg_flags:
        return 0

    bot_token = resolve_bot_token(bot_token, workspace)
    if not bot_token:
        print("Bot token not found (tried --bot-token, .env, TELEGRAM_BOT_TOKEN, openclaw.json, tgcm/.config.json)", file=sys.stderr)
        return 1

    channel_id = meta.get("channelId")
    if channel_id is None:
        print("Channel is not bound to a Telegram channel", file=sys.stderr)
        return 1

    # --chat
    if flags["chat"]:
        chat = tg_api_call(bot_token, "getChat", {"chat_id": channel_id})
        if chat:
            print("Chat:")
            print(f"  Title:       {chat.get('title', '(none)')}")
            username = chat.get("username")
            print(f"  Username:    @{username}" if username else "  Username:    (none)")
            print(f"  Description: {chat.get('description') or '(none)'}")
            print(f"  Invite link: {chat.get('invite_link') or '(none)'}")
            linked = chat.get("linked_chat_id")
            print(f"  Linked chat: {linked}" if linked else "  Linked chat: (none)")
        else:
            print("Chat: (API error)", file=sys.stderr)

    # --subscribers
    if flags["subscribers"]:
        count = tg_api_call(bot_token, "getChatMemberCount", {"chat_id": channel_id})
        if count is not None:
            print(f"Subscribers: {count}")
        else:
            print("Subscribers: (API error)", file=sys.stderr)

    # --permissions
    if flags["permissions"]:
        me = tg_api_call(bot_token, "getMe")
        if me:
            bot_id = me["id"]
            member = tg_api_call(bot_token, "getChatMember", {
                "chat_id": channel_id, "user_id": bot_id,
            })
            if member:
                print("Bot permissions:")
                print(f"  Role:              {member.get('status', 'unknown')}")
                print(f"  Post messages:     {_yn(member.get('can_post_messages'))}")
                print(f"  Edit messages:     {_yn(member.get('can_edit_messages'))}")
                print(f"  Delete messages:   {_yn(member.get('can_delete_messages'))}")
                print(f"  Invite users:      {_yn(member.get('can_invite_users'))}")
                print(f"  Restrict members:  {_yn(member.get('can_restrict_members'))}")
                print(f"  Promote members:   {_yn(member.get('can_promote_members'))}")
                print(f"  Manage chat:       {_yn(member.get('can_manage_chat'))}")
                print(f"  Change info:       {_yn(member.get('can_change_info'))}")
                print(f"  Manage video chat: {_yn(member.get('can_manage_video_chats'))}")
                print(f"  Post stories:      {_yn(member.get('can_post_stories'))}")
                print(f"  Edit stories:      {_yn(member.get('can_edit_stories'))}")
                print(f"  Delete stories:    {_yn(member.get('can_delete_stories'))}")
                print(f"  Anonymous:         {_yn(member.get('is_anonymous'))}")
            else:
                print("Bot permissions: (API error)", file=sys.stderr)
        else:
            print("Bot permissions: (API error — getMe failed)", file=sys.stderr)

    # --admins
    if flags["admins"]:
        admins = tg_api_call(bot_token, "getChatAdministrators", {"chat_id": channel_id})
        if admins is not None:
            print("Admins:")
            for a in admins:
                user = a.get("user", {})
                uname = f"@{user['username']}" if user.get("username") else user.get("first_name", "?")
                status = a.get("status", "administrator")
                bot_tag = " — bot" if user.get("is_bot") else ""
                print(f"  {uname} ({status}){bot_tag}")
        else:
            print("Admins: (API error)", file=sys.stderr)

    return 0


def load_local_config(workspace):
    """Load tgcm/.config.json. Returns dict (empty if missing)."""
    path = os.path.join(get_tgcm_root(workspace), ".config.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_local_config(workspace, config):
    """Save tgcm/.config.json."""
    root = get_tgcm_root(workspace)
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, ".config.json")
    with open(path, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def config_cmd(workspace, action, key=None, value=None):
    """Handle config set/get/list subcommand."""
    if action == "list":
        cfg = load_local_config(workspace)
        if not cfg:
            print("(no settings saved)")
            return 0
        reverse = {v: k for k, v in CONFIG_KEYS.items()}
        for json_key, val in cfg.items():
            display_key = reverse.get(json_key, json_key)
            print(f"{display_key}: {val}")
        return 0

    if not key:
        print("Key is required for config set/get", file=sys.stderr)
        return 1

    json_key = CONFIG_KEYS.get(key)
    if not json_key:
        valid = ", ".join(CONFIG_KEYS.keys())
        print(f"Unknown key '{key}'. Valid keys: {valid}", file=sys.stderr)
        return 1

    if action == "get":
        cfg = load_local_config(workspace)
        val = cfg.get(json_key)
        print(val if val is not None else "(not set)")
        return 0

    if action == "set":
        if value is None:
            print(f"Value is required: tgcm.py config set {key} <value>", file=sys.stderr)
            return 1
        cfg = load_local_config(workspace)
        cfg[json_key] = value
        save_local_config(workspace, cfg)
        print(f"[ok] {key} saved to tgcm/.config.json")
        return 0

    print(f"Unknown config action '{action}'. Use: set, get, list", file=sys.stderr)
    return 1


def find_openclaw_config():
    """Search for openclaw.json in standard locations. Returns path or None.

    Searches in order:
    1. Current directory (cwd)
    2. Home directory (~/.openclaw/openclaw.json)
    """
    candidates = [
        os.path.join(os.getcwd(), "openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json"),
    ]
    for path in candidates:
        resolved = os.path.realpath(path)
        if os.path.isfile(resolved):
            return resolved
    return None


def get_bot_token_from_config(config_path):
    """Extract channels.telegram.botToken from openclaw.json. Returns token or None."""
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return data["channels"]["telegram"]["botToken"]
    except (KeyError, json.JSONDecodeError, OSError, TypeError):
        return None


def load_dotenv_file(workspace="."):
    """Load .env file from workspace root. Returns dict of key=value pairs."""
    env_path = os.path.join(os.path.abspath(workspace), ".env")
    result = {}
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Strip surrounding quotes
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                result[key] = value
    except OSError:
        pass
    return result


def resolve_bot_token(cli_arg, workspace="."):
    """Resolve bot token: CLI arg → .env → TELEGRAM_BOT_TOKEN env → openclaw.json → tgcm/.config.json."""
    if cli_arg:
        return cli_arg
    dotenv = load_dotenv_file(workspace)
    if dotenv.get("TELEGRAM_BOT_TOKEN"):
        return dotenv["TELEGRAM_BOT_TOKEN"]
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_token:
        return env_token
    config_path = find_openclaw_config()
    if config_path:
        token = get_bot_token_from_config(config_path)
        if token:
            return token
    local = load_local_config(workspace)
    if local.get("botToken") is not None:
        return local["botToken"]
    return None


def resolve_token_source(cli_arg, workspace="."):
    """Return (token, source_label) or (None, None)."""
    if cli_arg:
        return cli_arg, "--bot-token arg"
    dotenv = load_dotenv_file(workspace)
    if dotenv.get("TELEGRAM_BOT_TOKEN"):
        return dotenv["TELEGRAM_BOT_TOKEN"], ".env"
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_token:
        return env_token, "TELEGRAM_BOT_TOKEN env"
    config_path = find_openclaw_config()
    if config_path:
        token = get_bot_token_from_config(config_path)
        if token:
            return token, f"openclaw.json ({config_path})"
    local = load_local_config(workspace)
    if local.get("botToken") is not None:
        return local["botToken"], "tgcm/.config.json"
    return None, None


def preflight_check(workspace, cli_bot_token):
    """Run preflight checks: bot token, getMe, SEARXNG_URL, channels."""
    has_fail = False

    # 1. Bot token
    token, source = resolve_token_source(cli_bot_token, workspace)
    if token:
        print(f"[ok]   Bot token: found (via {source})")
    else:
        print("[fail] Bot token: not found (tried --bot-token, .env, TELEGRAM_BOT_TOKEN, openclaw.json, tgcm/.config.json)")
        print("       Fix: run tgcm.py config set bot-token <your-token>")
        has_fail = True

    # 2. getMe
    bot_info = None
    if token:
        bot_info = tg_api_call(token, "getMe")
        if bot_info:
            uname = f"@{bot_info['username']}" if bot_info.get("username") else bot_info.get("first_name", "?")
            print(f"[ok]   Bot: {uname} (id: {bot_info['id']})")
        else:
            print("[fail] Bot: getMe failed — token may be invalid")
            print("       Fix: verify the token value or generate a new one via @BotFather")
            has_fail = True

    # 3. SEARXNG_URL
    searxng = os.environ.get("SEARXNG_URL")
    if not searxng:
        searxng = load_local_config(workspace).get("searxngUrl")
    if searxng:
        print(f"[ok]   SEARXNG_URL: {searxng}")
    else:
        print("[warn] SEARXNG_URL: not set (scout won't work)")
        print("       Fix: run tgcm.py config set searxng-url <url>")

    # 4. Channels
    root = get_tgcm_root(workspace)
    if not os.path.isdir(root):
        print("[warn] No tgcm/ directory — no channels initialized")
        print("       Fix: run tgcm.py init <name> to create a channel")
        return 1 if has_fail else 0

    channel_dirs = []
    for entry in sorted(os.listdir(root)):
        meta_path = os.path.join(root, entry, "channel.json")
        if os.path.isfile(meta_path):
            try:
                meta = load_channel_meta(os.path.join(root, entry))
                channel_dirs.append(meta)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                print(f"[warn] skipping {entry}: {e}", file=sys.stderr)
                continue

    if not channel_dirs:
        print("[warn] No channels found")
        print("       Fix: run tgcm.py init <name> to create a channel")
        return 1 if has_fail else 0

    for ch in channel_dirs:
        name = ch["name"]
        channel_id = ch.get("channelId")
        if channel_id is None:
            print(f'[warn] Channel "{name}": not bound (no channelId)')
            print(f'       Fix: run tgcm.py bind {name} --channel-id <id>')
            continue

        if not token or not bot_info:
            print(f'[warn] Channel "{name}": bound to {channel_id}, but cannot verify (no valid bot token)')
            continue

        # getChat — check type
        chat = tg_api_call(token, "getChat", {"chat_id": channel_id})
        if not chat:
            print(f'[fail] Channel "{name}": bound to {channel_id}, but getChat failed')
            print(f'       Fix: verify channel-id {channel_id} is correct and bot has access')
            has_fail = True
            continue

        chat_type = chat.get("type", "unknown")
        type_note = ""
        if chat_type != "channel":
            type_note = f" — WARNING: type={chat_type}, expected channel"
            has_fail = True

        # getChatMember — check bot is admin
        member = tg_api_call(token, "getChatMember", {
            "chat_id": channel_id, "user_id": bot_info["id"],
        })
        if member:
            status = member.get("status", "unknown")
            if status in ("administrator", "creator"):
                if type_note:
                    print(f'[fail] Channel "{name}": bound to {channel_id}, type={chat_type}, bot is {status}{type_note}')
                else:
                    print(f'[ok]   Channel "{name}": bound to {channel_id}, type={chat_type}, bot is {status}')
            else:
                print(f'[fail] Channel "{name}": bound to {channel_id}, bot status={status} (not admin)')
                print(f'       Fix: promote the bot to admin in channel {channel_id}')
                has_fail = True
        else:
            print(f'[fail] Channel "{name}": bound to {channel_id}, getChatMember failed')
            print(f'       Fix: verify bot has access to channel {channel_id}')
            has_fail = True

    return 1 if has_fail else 0


def get_id(identifier, bot_token, workspace="."):
    """Look up a Telegram chat by @username or numeric ID."""
    bot_token = resolve_bot_token(bot_token, workspace)
    if not bot_token:
        print("Bot token not found (tried --bot-token, .env, TELEGRAM_BOT_TOKEN, openclaw.json, tgcm/.config.json)", file=sys.stderr)
        return 1

    result = tg_api_call(bot_token, "getChat", {"chat_id": identifier})
    if not result:
        print(f"Could not resolve '{identifier}' — check the username/ID and bot token", file=sys.stderr)
        return 1

    print(f"id:       {result['id']}")
    chat_type = result.get('type', '(unknown)')
    print(f"type:     {chat_type}")
    print(f"title:    {result.get('title', '(none)')}")
    username = result.get("username")
    print(f"username: @{username}" if username else "username: (none)")
    if chat_type != "channel":
        print(f'\n\u26a0 This is a "{chat_type}", not a channel. tg-channel-manager works with channels only.')
    return 0


def event_connect(workspace, channel_id, channel_title=None):
    """Handle #tgcm connect event from Telegram."""
    root = get_tgcm_root(workspace)

    # Check if any channel is already bound to this ID
    if os.path.isdir(root):
        for entry in os.listdir(root):
            meta_path = os.path.join(root, entry, "channel.json")
            if os.path.isfile(meta_path):
                try:
                    meta = load_channel_meta(os.path.join(root, entry))
                    if meta.get("channelId") == channel_id:
                        print(
                            json.dumps(
                                {
                                    "status": "already_connected",
                                    "channel": meta["name"],
                                    "channelId": channel_id,
                                },
                                ensure_ascii=False,
                            )
                        )
                        return 0
                except (json.JSONDecodeError, KeyError, OSError) as e:
                    print(f"[warn] skipping {entry}: {e}", file=sys.stderr)
                    continue

    title_part = f" ({channel_title})" if channel_title else ""
    result = {
        "status": "new_channel",
        "channelId": channel_id,
        "instructions": (
            f"Channel {channel_id}{title_part} wants to connect.\n"
            f"Run: tgcm.py init <name> && "
            f"tgcm.py bind <name> --channel-id {channel_id}"
        ),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


def strip_html_tags(html_text):
    """Strip HTML tags and decode basic entities."""
    text = re.sub(r'<br\s*/?>', '\n', html_text)
    text = re.sub(r'<[^>]+>', '', text)
    for entity, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                          ('&quot;', '"'), ('&#39;', "'"), ('&nbsp;', ' ')]:
        text = text.replace(entity, char)
    def _safe_chr_hex(m):
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)

    def _safe_chr_dec(m):
        try:
            return chr(int(m.group(1)))
        except (ValueError, OverflowError):
            return m.group(0)

    text = re.sub(r'&#x([0-9a-fA-F]{1,6});', _safe_chr_hex, text)
    text = re.sub(r'&#(\d{1,7});', _safe_chr_dec, text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _escape_html(text):
    """Escape &, <, > for Telegram HTML."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _apply_inline(text):
    """Apply inline markdown transforms on already-escaped text.

    Converts **bold** → <b>bold</b> and `code` → <code>code</code>.
    """
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


def md_to_tg_html(text):
    """Convert markdown text to Telegram-compatible HTML.

    Supports: ### headers → <b>, **bold** → <b>, > quotes → <blockquote>,
    `code` → <code>. Preserves paragraph breaks.
    """
    lines = text.split("\n")
    result = []
    bq_buffer = []

    def _flush_bq():
        if bq_buffer:
            inner = "\n".join(bq_buffer)
            result.append(f"<blockquote>{inner}</blockquote>")
            bq_buffer.clear()

    for line in lines:
        stripped = line.strip()

        # Blockquote line
        if stripped.startswith(">"):
            content = stripped[1:].lstrip()
            content = _escape_html(content)
            content = _apply_inline(content)
            bq_buffer.append(content)
            continue

        _flush_bq()

        # Header line
        header_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if header_match:
            header_text = header_match.group(2)
            # Strip bold markers — header is already bold
            header_text = header_text.replace("**", "")
            header_text = _escape_html(header_text)
            header_text = _apply_inline(header_text)
            result.append(f"<b>{header_text}</b>")
            continue

        # Regular line
        escaped = _escape_html(line)
        result.append(_apply_inline(escaped))

    _flush_bq()
    return "\n".join(result)


def fetch_tme_page(username, before=None):
    """Fetch t.me/s/<username> HTML page. Returns HTML string."""
    url = f"https://t.me/s/{username}"
    if before:
        url += "?" + urllib.parse.urlencode({"before": before})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_tme_posts(html):
    """Parse posts from t.me/s/ HTML. Returns list of {msgId, text, links, date}."""
    posts = []
    blocks = re.split(r'(?=data-post=")', html)
    for block in blocks:
        msg_match = re.search(r'data-post="[^/]+/(\d+)"', block)
        if not msg_match:
            continue
        msg_id = int(msg_match.group(1))

        # Find the text div and extract full content respecting nesting
        text_open = re.search(
            r'class="tgme_widget_message_text[^"]*"[^>]*>', block,
        )
        raw = ""
        if text_open:
            after = block[text_open.end():]
            depth = 1
            pos = None
            for m in re.finditer(r'<div[^>]*>|</div>', after):
                if m.group().startswith('</'):
                    depth -= 1
                else:
                    depth += 1
                if depth == 0:
                    pos = m.start()
                    break
            raw = after[:pos] if pos is not None else after
        text = strip_html_tags(raw) if text_open else ""

        links = []
        if text_open:
            links = re.findall(r'href="(https?://[^"]+)"', raw)

        date_match = re.search(r'datetime="([^"]+)"', block)
        date = date_match.group(1) if date_match else ""

        if len(text) < MIN_POST_LENGTH:
            continue

        posts.append({
            "msgId": msg_id,
            "text": text,
            "links": links,
            "date": date,
        })
    return posts


def fetch_posts_cmd(workspace, name, bot_token, limit, dry_run):
    """Fetch posts from t.me/s/ and add to dedup index."""
    channel_dir = get_channel_dir(workspace, name)
    if not os.path.isdir(channel_dir):
        print(f"Channel '{name}' not found", file=sys.stderr)
        return 1

    try:
        meta = load_channel_meta(channel_dir)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading channel.json: {e}", file=sys.stderr)
        return 1
    channel_id = meta.get("channelId")
    if not channel_id:
        print(f"Channel '{name}' is not bound (no channelId)", file=sys.stderr)
        return 1

    bot_token = resolve_bot_token(bot_token, workspace)
    if not bot_token:
        print("Bot token not found", file=sys.stderr)
        return 1

    chat = tg_api_call(bot_token, "getChat", {"chat_id": channel_id})
    if not chat:
        print(f"getChat failed for {channel_id}", file=sys.stderr)
        return 1

    username = chat.get("username")
    if not username:
        print("Channel has no @username (private channels not supported)", file=sys.stderr)
        return 1

    print(f"Fetching posts from @{username}...")

    # Load existing index
    index_path = os.path.join(channel_dir, "content-index.json")
    wrapper = None
    index_posts = []
    if os.path.exists(index_path):
        try:
            with open(index_path, "r") as f:
                index_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading index: {e}", file=sys.stderr)
            return 1
        if isinstance(index_data, dict) and "posts" in index_data:
            index_posts = index_data["posts"]
            wrapper = index_data
        else:
            index_posts = index_data
    if wrapper is None:
        wrapper = {"version": 1, "posts": index_posts}

    existing_ids = {p["msgId"] for p in index_posts}

    # Fetch pages
    all_posts = []
    min_id = None
    for page in range(1, limit + 1):
        try:
            html = fetch_tme_page(username, before=min_id)
        except (urllib.error.URLError, OSError) as e:
            print(f"  Page {page}: fetch error — {e}", file=sys.stderr)
            break

        posts = parse_tme_posts(html)
        if not posts:
            if page == 1:
                print("  No posts found on the channel page")
            break

        ids = [p["msgId"] for p in posts]
        print(f"  Page {page}: {len(posts)} posts (IDs {min(ids)}-{max(ids)})")
        all_posts.extend(posts)
        min_id = min(ids)

        # t.me/s/ serves ~20 posts per page; fewer means we've reached the beginning
        if len(posts) < MIN_PAGE_SIZE:
            break

    if not all_posts:
        print("No posts found")
        return 0

    # Add new posts to index
    new_count = 0
    skip_count = 0
    for post in all_posts:
        if post["msgId"] in existing_ids:
            skip_count += 1
            continue

        topic = post["text"].split("\n")[0][:200]
        keywords = list(set(re.findall(r'[^\W\d_]{4,}', topic.lower(), re.UNICODE)))

        if not dry_run:
            index_posts.append({
                "msgId": post["msgId"],
                "topic": topic,
                "links": post["links"],
                "keywords": keywords,
            })
            existing_ids.add(post["msgId"])
        new_count += 1

    if not dry_run and new_count > 0:
        index_posts.sort(key=lambda x: x["msgId"])
        wrapper["posts"] = index_posts
        with open(index_path, "w") as f:
            json.dump(wrapper, f, ensure_ascii=False, indent=2)

    action = "Would add" if dry_run else "Added"
    print(f"{action} {new_count} new posts to index ({skip_count} already existed)")
    return 0


def build_parser():
    """Build the argparse parser."""
    parser = argparse.ArgumentParser(
        description="Multi-channel management for tg-channel-manager"
    )
    parser.add_argument(
        "--workspace", type=str, default=".",
        help="Path to workspace root",
    )
    parser.add_argument(
        "--bot-token", type=str, default=None,
        help="Telegram Bot API token",
    )

    subparsers = parser.add_subparsers(dest="command")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new channel")
    init_parser.add_argument("name", help="Channel name")

    # list
    subparsers.add_parser("list", help="List all channels")

    # bind
    bind_parser = subparsers.add_parser("bind", help="Bind channel to Telegram")
    bind_parser.add_argument("name", help="Channel name")
    bind_parser.add_argument(
        "--channel-id", required=True, help="Telegram channel ID"
    )

    # info
    info_parser = subparsers.add_parser("info", help="Show channel information")
    info_parser.add_argument("name", help="Channel name")
    info_parser.add_argument("--chat", action="store_true", help="Show chat data from Telegram API")
    info_parser.add_argument("--subscribers", action="store_true", help="Show subscriber count")
    info_parser.add_argument("--permissions", action="store_true", help="Show bot permissions")
    info_parser.add_argument("--admins", action="store_true", help="Show channel admins")
    info_parser.add_argument("--all", action="store_true", help="Enable all Telegram API flags")

    # get-id
    getid_parser = subparsers.add_parser(
        "get-id", help="Look up Telegram chat by @username or ID"
    )
    getid_parser.add_argument(
        "identifier", help="@username or numeric chat ID"
    )

    # check
    subparsers.add_parser("check", help="Preflight: verify bot token, channels, env vars")

    # config
    config_parser = subparsers.add_parser(
        "config", help="Manage local settings (bot-token, searxng-url)"
    )
    config_parser.add_argument(
        "action", nargs="?", default="list",
        choices=["set", "get", "list"],
        help="Action: set, get, or list",
    )
    config_parser.add_argument("key", nargs="?", default=None, help="Setting key")
    config_parser.add_argument("value", nargs="?", default=None, help="Setting value (for set)")

    # fetch-posts
    fetch_parser = subparsers.add_parser(
        "fetch-posts", help="Load channel posts into dedup index",
    )
    fetch_parser.add_argument("name", help="Channel name")
    fetch_parser.add_argument(
        "--limit", type=int, default=5,
        help="Max pages to fetch (default: 5)",
    )
    fetch_parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview only, don't add to index",
    )

    # connect
    connect_parser = subparsers.add_parser(
        "connect", help="Handle #tgcm connect event"
    )
    connect_parser.add_argument(
        "--channel-id", required=True, help="Telegram channel ID"
    )
    connect_parser.add_argument(
        "--channel-title", default=None, help="Channel title (optional)"
    )

    # publish
    publish_parser = subparsers.add_parser(
        "publish", help="Publish post to channel (auto-splits long text with photo)"
    )
    publish_parser.add_argument("name", help="Channel name")
    publish_parser.add_argument(
        "--text", required=True, help="Post text"
    )
    publish_parser.add_argument(
        "--photo", default=None, help="Photo URL (optional)"
    )
    publish_parser.add_argument(
        "--parse-mode", default=None, help="Parse mode: HTML or MarkdownV2 (optional)"
    )
    publish_parser.add_argument(
        "--format", default="md", choices=["md", "plain"],
        help="Text format: 'md' converts markdown to HTML (default), 'plain' sends as-is"
    )
    publish_parser.add_argument(
        "--source", default=None,
        help="Source URL to append as link (optional; overrides Source from --post-id)"
    )
    publish_parser.add_argument(
        "--post-id", default=None, type=int,
        help="Post number in content-queue.md (enables auto-Source and auto-status update)"
    )

    # validate
    validate_parser = subparsers.add_parser(
        "validate", help="Validate content-queue format and statuses"
    )
    validate_parser.add_argument("name", help="Channel name")
    validate_parser.add_argument(
        "--fix", action="store_true", help="Auto-fix status inconsistencies"
    )

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "init":
        return channel_init(args.workspace, args.name)

    if args.command == "list":
        return channel_list(args.workspace)

    if args.command == "bind":
        return channel_bind(args.workspace, args.name, args.channel_id)

    if args.command == "info":
        flags = {
            "chat": args.chat or args.all,
            "subscribers": args.subscribers or args.all,
            "permissions": args.permissions or args.all,
            "admins": args.admins or args.all,
        }
        return channel_info(args.workspace, args.name, args.bot_token, flags)

    if args.command == "check":
        return preflight_check(args.workspace, args.bot_token)

    if args.command == "config":
        return config_cmd(args.workspace, args.action, args.key, args.value)

    if args.command == "get-id":
        return get_id(args.identifier, args.bot_token, args.workspace)

    if args.command == "fetch-posts":
        return fetch_posts_cmd(
            args.workspace, args.name, args.bot_token,
            args.limit, args.dry_run,
        )

    if args.command == "connect":
        return event_connect(
            args.workspace,
            args.channel_id,
            channel_title=args.channel_title,
        )

    if args.command == "publish":
        channel_dir = get_channel_dir(args.workspace, args.name)
        if not os.path.isdir(channel_dir):
            print(f"Channel '{args.name}' not found", file=sys.stderr)
            return 1
        try:
            meta = load_channel_meta(channel_dir)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading channel.json: {e}", file=sys.stderr)
            return 1
        channel_id = meta.get("channelId")
        if not channel_id:
            print(f"Channel '{args.name}' is not bound (no channelId)", file=sys.stderr)
            return 1
        bot_token = resolve_bot_token(args.bot_token, args.workspace)
        if not bot_token:
            print("Bot token not found", file=sys.stderr)
            return 1

        # Resolve source_url and queue post info
        source_url = args.source
        queue_path = os.path.join(channel_dir, "content-queue.md")
        post_id = args.post_id
        can_update_status = False

        if post_id is not None:
            try:
                with open(queue_path, "r", encoding="utf-8") as f:
                    queue_content = f.read()
                post_info = _find_queue_post(queue_content, post_id)
                if post_info:
                    if not source_url and post_info.get("source"):
                        source_url = post_info["source"]
                    can_update_status = True
                else:
                    print(f"Warning: post #{post_id} not found in content-queue.md", file=sys.stderr)
            except OSError:
                print("Warning: content-queue.md not found", file=sys.stderr)

        results = publish_post(
            bot_token, channel_id, args.text,
            photo_url=args.photo, parse_mode=args.parse_mode,
            text_format=args.format, source_url=source_url,
        )
        if not results:
            return 1

        # Update status in content-queue.md after successful publish
        status_updated = False
        if post_id is not None and can_update_status:
            status_updated = _update_queue_status(queue_path, post_id, "published")
            if not status_updated:
                print(f"Warning: failed to update status for post #{post_id}", file=sys.stderr)

        ids = [r["message_id"] for r in results]
        output = {"ok": True, "message_ids": ids}
        if source_url:
            output["source"] = source_url
        if post_id is not None:
            output["status_updated"] = status_updated
        print(json.dumps(output))
        return 0

    if args.command == "validate":
        channel_dir = get_channel_dir(args.workspace, args.name)
        if not os.path.isdir(channel_dir):
            print(f"Channel '{args.name}' not found", file=sys.stderr)
            return 1
        validate_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "validate-queue.py"
        )
        spec = importlib.util.spec_from_file_location("validate_queue", validate_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.main(["--base-dir", channel_dir] + (["--fix"] if args.fix else []))

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
