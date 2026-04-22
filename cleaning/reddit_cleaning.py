import html
import re
from pathlib import Path

import pandas as pd

# Set this to either:
# - a single .txt file
# - or a folder containing multiple .txt files
INPUT_PATH = "../data/raw/reddit"
OUTPUT_FILE = "../data/cleaned/reddit_clean.csv"

# If True, duplicate comments are only removed within the same topic.
# If False, duplicate comments are removed across the entire dataset.
DEDUP_WITHIN_TOPIC = True

# -------------------------------------------------------------------
# CUSTOM TOPIC RULES
# -------------------------------------------------------------------
# How to use:
# - key: normalized topic name you want to target
# - aliases: alternative names for that topic/product
# - include_any: comment must contain at least one of these
# - include_all: comment must contain all of these
# - exclude_any: comment must NOT contain any of these
# - min_score: minimum reddit score required
#
# If a topic has no custom rule, the script falls back to the old behavior:
# keep comments that contain meaningful words from the topic.
#
# Example:
# "ag1 powder" will keep comments mentioning ag1 / athletic greens,
# but drop comments that are just about Huberman / NYT article discourse.
TOPIC_RULES = {
    "ag1 powder": {
        "aliases": ["ag1", "athletic greens", "greens powder"],
        "include_any": ["ag1", "athletic greens", "greens powder"],
        "include_all": [],
        "exclude_any": [],
        "min_score": 0,
    },
    "betterhelp": {
        "aliases": ["betterhelp", "better help"],
        "include_any": ["betterhelp", "better help"],
        "include_all": [],
        "exclude_any": [],
        "min_score": 0,
    },
    "LMNT": {
        "aliases": ["lmnt"],
        "include_any": [],
        "include_all": [],
        "exclude_any": [],
        "min_score": 0,
    },
    "magic spoon": {
        "aliases": ["magicspoon", "magic spoon cereal"],
        "include_any": ["magic"],
        "include_all": [],
        "exclude_any": [],
        "min_score": 0,
    },
}

TOPIC_RE = re.compile(r"^Reddit User Reviews:\s*(.+?)\s*$")
TOP_COMMENTS_RE = re.compile(r"^TOP\s+\d+\s+COMMENTS:\s*$")
NO_COMMENTS_RE = re.compile(r"^No comments found\.?\s*$")
POST_RE = re.compile(r"^POST\s+#\d+\s*$")
SEPARATOR_RE = re.compile(r"^\s*(=+|-{10,})\s*$")
COMMENT_HEADER_RE = re.compile(r"^\s*\[\d+\]\s+u/([^\s]+)\s+\(score:\s*(-?\d+)\)\s*$")


def clean_reddit(text):
    """
    Clean reddit comment text similar to Twitter cleaning:
    - lowercase
    - remove URLs
    - remove user mentions
    - remove hashtag symbol
    - remove punctuation/special chars
    - remove extra spaces
    """
    if pd.isna(text):
        return ""

    text = html.unescape(str(text))
    text = text.replace("\u200b", " ")
    text = text.lower()
    text = re.sub(r"https?://\S+|www\.\S+", "", text)  # remove URLs
    text = re.sub(r"u\/\w+", "", text)  # remove reddit user mentions
    text = re.sub(r"@\w+", "", text)  # remove @mentions just in case
    text = re.sub(r"#", "", text)  # remove hashtag symbol only
    text = re.sub(r"[^\w\s]", "", text)  # remove punctuation/special chars
    text = " ".join(text.split())  # remove extra spaces
    return text


def normalize_text(text):
    """
    Light cleanup before storing raw parsed comment text.
    """
    text = html.unescape(str(text))
    text = text.replace("\u200b", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def should_skip_comment(username, comment_text):
    if not comment_text:
        return True

    if username.lower() == "automoderator":
        return True

    if username == "[deleted]":
        return True

    lowered = comment_text.lower().strip()
    if lowered in {"[removed]", "[deleted]"}:
        return True

    return False


def normalize_terms(values):
    """
    Clean a list of rule terms the same way comments are cleaned.
    """
    return [clean_reddit(v) for v in values if clean_reddit(v)]


def contains_any(text, terms):
    return any(term in text for term in terms)


def contains_all(text, terms):
    return all(term in text for term in terms)


def get_topic_rule(topic):
    """
    Return the matching custom rule for a topic, if one exists.
    Matches against the rule key and aliases after cleaning.
    """
    topic_clean = clean_reddit(topic)

    for rule_topic, rule in TOPIC_RULES.items():
        rule_topic_clean = clean_reddit(rule_topic)
        aliases_clean = normalize_terms(rule.get("aliases", []))

        if topic_clean == rule_topic_clean or topic_clean in aliases_clean:
            return rule

    return None


def default_topic_match(comment, topic):
    """
    Fallback behavior:
    keep row only if the cleaned comment includes a meaningful topic word.
    Example:
      topic = 'AG1 Powder'
      comment contains 'ag1' -> keep
    """
    comment_clean = clean_reddit(comment)
    topic_clean = clean_reddit(topic)

    if not comment_clean or not topic_clean:
        return False

    topic_words = topic_clean.split()

    # Keep meaningful words only
    topic_words = [
        word
        for word in topic_words
        if len(word) >= 3 or any(ch.isdigit() for ch in word)
    ]

    if not topic_words:
        return False

    comment_words = set(comment_clean.split())
    return any(word in comment_words for word in topic_words)


def should_keep_topic_comment(comment, topic, score):
    """
    Apply custom topic rules if available.
    If no custom rule exists for the topic, fall back to default topic matching.
    """
    comment_clean = clean_reddit(comment)
    topic_clean = clean_reddit(topic)

    if not comment_clean or not topic_clean:
        return False

    rule = get_topic_rule(topic_clean)

    if rule is None:
        return default_topic_match(comment_clean, topic_clean)

    aliases = normalize_terms(rule.get("aliases", []))
    include_any = normalize_terms(rule.get("include_any", []))
    include_all = normalize_terms(rule.get("include_all", []))
    exclude_any = normalize_terms(rule.get("exclude_any", []))
    min_score = rule.get("min_score", None)

    # Optional score threshold
    if min_score is not None and score < min_score:
        return False

    # Exclude unwanted comments first
    if exclude_any and contains_any(comment_clean, exclude_any):
        return False

    # Require all phrases if specified
    if include_all and not contains_all(comment_clean, include_all):
        return False

    # Require at least one include phrase / alias if specified
    required_any = include_any + aliases
    if required_any and not contains_any(comment_clean, required_any):
        return False

    return True


def extract_comments_from_text(text, fallback_topic="unknown"):
    lines = text.splitlines()
    rows = []

    topic = fallback_topic
    in_comment_section = False
    current_user = None
    current_score = None
    current_lines = []

    def flush_comment():
        nonlocal current_user, current_score, current_lines, rows

        if current_user is None:
            return

        raw_comment = normalize_text(" ".join(current_lines))

        if not should_skip_comment(current_user, raw_comment):
            rows.append(
                {
                    "reddit": raw_comment,
                    "topic": topic,
                    "score": current_score,
                }
            )

        current_user = None
        current_score = None
        current_lines = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        topic_match = TOPIC_RE.match(stripped)
        if topic_match:
            topic = topic_match.group(1).strip()
            continue

        if TOP_COMMENTS_RE.match(stripped):
            flush_comment()
            in_comment_section = True
            continue

        if NO_COMMENTS_RE.match(stripped):
            flush_comment()
            in_comment_section = False
            continue

        if POST_RE.match(stripped):
            flush_comment()
            in_comment_section = False
            continue

        if SEPARATOR_RE.match(stripped):
            flush_comment()
            continue

        if in_comment_section:
            header_match = COMMENT_HEADER_RE.match(line)
            if header_match:
                flush_comment()
                current_user = header_match.group(1)
                current_score = int(header_match.group(2))
                current_lines = []
                continue

            if current_user is not None:
                cleaned_line = normalize_text(stripped)
                if cleaned_line:
                    current_lines.append(cleaned_line)

    flush_comment()
    return rows


def get_text_files(input_path):
    path = Path(input_path)

    if path.is_file():
        return [path]

    if path.is_dir():
        return sorted(path.glob("*.txt"))

    raise FileNotFoundError(f"Could not find: {input_path}")


def clean_reddit_export(input_path, output_file):
    all_rows = []

    for file_path in get_text_files(input_path):
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        fallback_topic = file_path.stem
        rows = extract_comments_from_text(text, fallback_topic=fallback_topic)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows, columns=["reddit", "topic", "score"])

    # Clean reddit comments
    df["reddit"] = df["reddit"].apply(clean_reddit)
    df["topic"] = df["topic"].apply(clean_reddit)

    # Remove blank rows after cleaning
    df = df[df["reddit"].str.strip() != ""]
    df = df[df["topic"].str.strip() != ""]

    # Apply topic-specific keep rules
    df = df[
        df.apply(
            lambda row: should_keep_topic_comment(
                row["reddit"], row["topic"], row["score"]
            ),
            axis=1,
        )
    ]

    # Remove duplicates
    if DEDUP_WITHIN_TOPIC:
        df = df.drop_duplicates(subset=["reddit", "topic"], keep="first")
    else:
        df = df.drop_duplicates(subset=["reddit"], keep="first")

    # Reorder columns
    df = df[["reddit", "topic", "score"]].reset_index(drop=True)

    # Save output
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"Cleaned CSV saved to: {output_file}")
    print(f"Rows kept: {len(df)}")


if __name__ == "__main__":
    clean_reddit_export(INPUT_PATH, OUTPUT_FILE)
