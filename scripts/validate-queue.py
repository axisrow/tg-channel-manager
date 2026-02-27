#!/usr/bin/env python3
"""
Validate content-queue.md format and cross-reference statuses with content-index.json.

Usage:
  python3 validate-queue.py --base-dir /path/to/channel [--fix] [--json]
"""

import argparse
import json
import os
import re
import sys
import unicodedata


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

POST_HEADER_RE = re.compile(r'^### (\d+)\s*$')
FIELD_RE = re.compile(r'^- \*\*(\w+):\*\*\s*(.*)')
URL_RE = re.compile(r'^https?://.+')

VALID_STATUSES = {'draft', 'pending', 'published'}
REQUIRED_FIELDS = {'Status', 'Rubric', 'Topic', 'Source'}

STOPWORDS = {
    'this', 'that', 'with', 'from', 'have', 'been', 'will', 'what', 'when',
    'which', 'their', 'about', 'would', 'could', 'should', 'more', 'some',
    'into', 'than', 'other', 'these', 'those', 'just', 'also', 'only',
    'agent', 'agents',
}


# ---------------------------------------------------------------------------
# Emoji detection
# ---------------------------------------------------------------------------

def _is_emoji(ch):
    """Return True if *ch* looks like an emoji (Unicode category So or specific ranges)."""
    cat = unicodedata.category(ch)
    if cat == 'So':
        return True
    cp = ord(ch)
    # Common emoji ranges not always categorised as So
    return (
        0x1F600 <= cp <= 0x1F64F or  # emoticons
        0x1F300 <= cp <= 0x1F5FF or  # misc symbols & pictographs
        0x1F680 <= cp <= 0x1F6FF or  # transport & map
        0x1F900 <= cp <= 0x1F9FF or  # supplemental symbols
        0x2600 <= cp <= 0x26FF or    # misc symbols
        0x2700 <= cp <= 0x27BF or    # dingbats
        0xFE00 <= cp <= 0xFE0F or    # variation selectors
        0x200D == cp                  # ZWJ
    )


def starts_with_emoji(text):
    """Return True if *text* starts with an emoji character."""
    if not text:
        return False
    return _is_emoji(text[0])


# ---------------------------------------------------------------------------
# Post parser
# ---------------------------------------------------------------------------

class Post:
    __slots__ = ('number', 'line', 'fields', 'text', 'field_lines')

    def __init__(self, number, line):
        self.number = number
        self.line = line          # 1-based line of "### N"
        self.fields = {}          # field_name -> value
        self.text = ''            # body after "- **Text:**"
        self.field_lines = {}     # field_name -> 1-based line number


def parse_queue(content):
    """Parse content-queue.md into a list of Post objects."""
    lines = content.split('\n')
    posts = []
    current = None
    in_text = False

    for i, raw in enumerate(lines):
        lineno = i + 1

        header_m = POST_HEADER_RE.match(raw)
        if header_m:
            current = Post(int(header_m.group(1)), lineno)
            posts.append(current)
            in_text = False
            continue

        if current is None:
            continue

        if in_text:
            current.text += raw + '\n'
            continue

        field_m = FIELD_RE.match(raw)
        if field_m:
            name, value = field_m.group(1), field_m.group(2).strip()
            current.fields[name] = value
            current.field_lines[name] = lineno
            if name == 'Text':
                in_text = True
            continue

    # trim trailing newlines from text bodies
    for p in posts:
        p.text = p.text.rstrip('\n')

    return posts


# ---------------------------------------------------------------------------
# Format validation
# ---------------------------------------------------------------------------

def validate_format(posts):
    """Return (errors, warnings) lists. Each item: (post_number, line, level, message)."""
    errors = []
    warnings = []
    seen_numbers = {}

    for post in posts:
        n = post.number

        # duplicate number
        if n in seen_numbers:
            errors.append((n, post.line, 'error',
                           f'duplicate post number (first at line {seen_numbers[n]})'))
        else:
            seen_numbers[n] = post.line

        # required fields
        for field in REQUIRED_FIELDS:
            if field not in post.fields:
                errors.append((n, post.line, 'error', f'missing field {field}'))

        # Status value
        status = post.fields.get('Status', '')
        if status and status not in VALID_STATUSES:
            errors.append((n, post.field_lines.get('Status', post.line), 'error',
                           f'invalid Status "{status}" (expected: {", ".join(sorted(VALID_STATUSES))})'))

        # Rubric emoji
        rubric = post.fields.get('Rubric', '')
        if rubric and not starts_with_emoji(rubric):
            errors.append((n, post.field_lines.get('Rubric', post.line), 'error',
                           'Rubric must start with an emoji'))

        # Topic not empty
        topic = post.fields.get('Topic', '')
        if 'Topic' in post.fields and not topic:
            errors.append((n, post.field_lines.get('Topic', post.line), 'error',
                           'Topic is empty'))

        # Source URL
        source = post.fields.get('Source', '')
        if source and not URL_RE.match(source):
            errors.append((n, post.field_lines.get('Source', post.line), 'error',
                           f'invalid Source URL: {source}'))

        # Image URL (optional field, warn if present but invalid)
        image = post.fields.get('Image', '')
        if image and not URL_RE.match(image):
            warnings.append((n, post.field_lines.get('Image', post.line), 'warning',
                             f'invalid Image URL: {image}'))

        # Text body
        if not post.text.strip():
            errors.append((n, post.line, 'error', 'empty post text'))

    return errors, warnings


# ---------------------------------------------------------------------------
# Index cross-reference  (reuses dedup-check.py logic)
# ---------------------------------------------------------------------------

def load_index(index_file):
    """Load content-index.json (supports versioned wrapper)."""
    if not os.path.exists(index_file):
        return []
    try:
        with open(index_file, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f'Warning: corrupt index {index_file}: {e}', file=sys.stderr)
        return []
    if isinstance(data, dict) and 'posts' in data:
        return data['posts']
    return data


def extract_keywords(text):
    """Extract keywords (4+ char words, no digits/underscore) minus stopwords."""
    words = set(re.findall(r'[^\W\d_]{4,}', text.lower(), re.UNICODE))
    return words - STOPWORDS


def normalize_url(url):
    return re.sub(r'https?://(www\.)?', '', url.rstrip('/'))


def find_in_index(post, index):
    """Check if a queue post matches any entry in the index.

    Returns the best match dict or None.
    """
    topic = post.fields.get('Topic', '')
    source = post.fields.get('Source', '')

    # --- link matching ---
    if source:
        norm_source = normalize_url(source)
        for entry in index:
            for link in entry.get('links', []):
                if normalize_url(link) == norm_source:
                    return {'msgId': entry['msgId'], 'topic': entry['topic'][:100],
                            'score': 1.0, 'method': 'link'}

    # --- topic matching ---
    if topic:
        topic_words = extract_keywords(topic)
        if not topic_words:
            return None

        best = None
        for entry in index:
            post_words = set(w.lower() for w in entry.get('keywords', []))
            post_words -= STOPWORDS
            if not post_words:
                continue

            overlap = topic_words & post_words
            topic_stems = {w[:5] for w in topic_words if len(w) >= 5}
            post_stems = {w[:5] for w in post_words if len(w) >= 5}
            stem_overlap = topic_stems & post_stems
            best_overlap = max(len(overlap), len(stem_overlap))
            score = best_overlap / min(len(topic_words), len(post_words))

            if score >= 0.4 and best_overlap >= 2:
                if best is None or score > best['score']:
                    best = {'msgId': entry['msgId'], 'topic': entry['topic'][:100],
                            'score': round(score, 2), 'method': 'topic'}
        return best

    return None


def save_index(index_file, index):
    """Save index list back to file, preserving versioned wrapper if present."""
    wrapper = None
    if os.path.exists(index_file):
        try:
            with open(index_file, 'r') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = None
        if isinstance(existing, dict) and 'version' in existing:
            wrapper = {'version': existing['version'], 'posts': index}
    with open(index_file, 'w') as f:
        json.dump(wrapper if wrapper else index, f, ensure_ascii=False, indent=2)


def check_statuses(posts, index):
    """Cross-reference post statuses with index. Returns (warnings, fixes, index_adds).

    fixes: list of (post_number, status_line, old_status) for --fix.
    index_adds: list of dicts to append to index for published posts missing from it.
    """
    warnings = []
    fixes = []
    index_adds = []

    for post in posts:
        status = post.fields.get('Status', '')
        match = find_in_index(post, index)

        if match and status != 'published':
            warnings.append((post.number, post.line, 'warning',
                             f'found in index (msg {match["msgId"]}, '
                             f'score {match["score"]}, {match["method"]}) '
                             f'but Status is "{status}"'))
            fixes.append((post.number, post.field_lines.get('Status', post.line), status))

        elif status == 'published' and not match:
            topic = post.fields.get('Topic', '')
            source = post.fields.get('Source', '')
            keywords = list(extract_keywords(topic))
            links = [source] if source else []
            index_adds.append({
                'msgId': 0,
                'topic': topic,
                'links': links,
                'keywords': keywords,
            })

        elif status == 'published' and match:
            warnings.append((post.number, post.line, 'warning',
                             'published post should be removed from queue'))

    return warnings, fixes, index_adds


# ---------------------------------------------------------------------------
# Auto-fix
# ---------------------------------------------------------------------------

def apply_fixes(content, fixes, posts):
    """Replace Status values for matched posts. Returns new content."""
    lines = content.split('\n')

    # Build a map: line_number (1-based) -> new status
    fix_map = {}
    for post_num, status_line, old_status in fixes:
        fix_map[status_line] = old_status

    changed = 0
    for lineno, old_status in fix_map.items():
        idx = lineno - 1
        if idx < len(lines):
            old_line = lines[idx]
            new_line = old_line.replace(f'**Status:** {old_status}', '**Status:** published')
            if new_line != old_line:
                lines[idx] = new_line
                changed += 1

    return '\n'.join(lines), changed


# ---------------------------------------------------------------------------
# CLI & main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Validate content-queue.md format and statuses')
    parser.add_argument('--base-dir', required=True,
                        help='Path to channel directory')
    parser.add_argument('--fix', action='store_true',
                        help='Auto-fix status inconsistencies')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')
    args = parser.parse_args(argv)

    base = os.path.abspath(args.base_dir)
    queue_path = os.path.join(base, 'content-queue.md')
    index_path = os.path.join(base, 'content-index.json')

    if not os.path.isfile(queue_path):
        print(f'Error: {queue_path} not found', file=sys.stderr)
        return 1

    with open(queue_path, 'r') as f:
        content = f.read()

    posts = parse_queue(content)

    # Format validation
    fmt_errors, fmt_warnings = validate_format(posts)

    # Index cross-reference
    index = load_index(index_path)
    status_warnings, fixes, index_adds = check_statuses(posts, index)

    # Auto-sync: add published posts missing from index
    if index_adds:
        index.extend(index_adds)
        index.sort(key=lambda x: x['msgId'])
        save_index(index_path, index)

    all_errors = fmt_errors
    all_warnings = fmt_warnings + status_warnings

    # --json output
    if args.json:
        result = {
            'posts': len(posts),
            'errors': [{'post': e[0], 'line': e[1], 'level': e[2], 'message': e[3]}
                       for e in all_errors],
            'warnings': [{'post': w[0], 'line': w[1], 'level': w[2], 'message': w[3]}
                         for w in all_warnings],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.fix and fixes:
            new_content, changed = apply_fixes(content, fixes, posts)
            if changed:
                with open(queue_path, 'w') as f:
                    f.write(new_content)
                result['fixed'] = changed
        return 1 if all_errors else 0

    # Human-readable output
    print(f'Validating content-queue.md ({len(posts)} posts)...')
    print()

    reported = set()
    ok_posts = set(p.number for p in posts)

    for e in all_errors:
        print(f'\u274c Post #{e[0]} (line {e[1]}): {e[3]}')
        reported.add(e[0])
        ok_posts.discard(e[0])

    for w in all_warnings:
        print(f'\u26a0\ufe0f  Post #{w[0]} (line {w[1]}): {w[3]}')
        reported.add(w[0])
        ok_posts.discard(w[0])

    # Apply fixes
    if args.fix and fixes:
        new_content, changed = apply_fixes(content, fixes, posts)
        if changed:
            with open(queue_path, 'w') as f:
                f.write(new_content)
            print(f'\n\U0001f527 Fixed {changed} status(es) → published')

    # Summary of OK posts
    if ok_posts:
        ok_list = _format_ranges(sorted(ok_posts))
        print(f'\u2705 Posts {ok_list} — format ok')

    print()
    summary = f'Summary: {len(posts)} posts, {len(all_errors)} error(s), {len(all_warnings)} warning(s)'
    if index_adds:
        summary += f'\n  (synced {len(index_adds)} post(s) to index)'
    print(summary)

    return 1 if all_errors else 0


def _format_ranges(numbers):
    """Format [1,2,3,5,7,8,9] as '#1–3, #5, #7–9'."""
    if not numbers:
        return ''
    ranges = []
    start = prev = numbers[0]
    for n in numbers[1:]:
        if n == prev + 1:
            prev = n
        else:
            ranges.append(f'#{start}' if start == prev else f'#{start}\u2013{prev}')
            start = prev = n
    ranges.append(f'#{start}' if start == prev else f'#{start}\u2013{prev}')
    return ', '.join(ranges)


if __name__ == '__main__':
    sys.exit(main())
