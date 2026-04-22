import html
import re
from pathlib import Path

import pandas as pd

# Set this to either:
# - a single .txt file
# - or a folder containing multiple .txt files
INPUT_PATH = "../data/raw/reddit"
OUTPUT_FILE = "reddit_comments_clean.csv"

TOPIC_RE = re.compile(r"^Reddit User Reviews:\s*(.+?)\s*$")
TOP_COMMENTS_RE = re.compile(r"^TOP\s+\d+\s+COMMENTS:\s*$")
NO_COMMENTS_RE = re.compile(r"^No comments found\.?\s*$")
POST_RE = re.compile(r"^POST\s+#\d+\s*$")
SEPARATOR_RE = re.compile(r"^\s*(=+|-{10,})\s*$")
COMMENT_HEADER_RE = re.compile(r"^\s*\[\d+\]\s+u/([^\s]+)\s+\(score:\s*(-?\d+)\)\s*$")


def clean_reddit(text):
    """
    Clean reddit comment text similar to Twitter cleaning.
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


def topic_in_comment(comment, topic):
    """
    Keep row only if the cleaned comment includes the topic.
    Uses topic words instead of requiring the whole phrase.
    Example:
      topic = 'AG1 Powder'
      comment contains 'ag1' -> keep
    """
    comment_clean = clean_reddit(comment)
    topic_clean = clean_reddit(topic)

    if not comment_clean or not topic_clean:
        return False

    topic_words = topic_clean.split()

    # keep meaningful words only
    topic_words = [
        w for w in topic_words if len(w) >= 3 or any(ch.isdigit() for ch in w)
    ]

    if not topic_words:
        return False

    return any(word in comment_clean.split() for word in topic_words)


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
            rows.append({"reddit": raw_comment, "topic": topic, "score": current_score})

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

    # Remove blank rows after cleaning
    df = df[df["reddit"].str.strip() != ""]

    # Remove rows where comment does not include the topic
    df = df[df.apply(lambda row: topic_in_comment(row["reddit"], row["topic"]), axis=1)]

    # Remove duplicates based on cleaned reddit comment
    df = df.drop_duplicates(subset=["reddit"], keep="first")

    # Reorder columns
    df = df[["reddit", "topic", "score"]].reset_index(drop=True)

    # Save output
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"Cleaned CSV saved to: {output_file}")


if __name__ == "__main__":
    clean_reddit_export(INPUT_PATH, OUTPUT_FILE)
