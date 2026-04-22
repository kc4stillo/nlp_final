# %%
import ast
import re

import pandas as pd
from langdetect import DetectorFactory, detect_langs

# make langdetect deterministic
DetectorFactory.seed = 0

# %%
tweets_raw = pd.read_csv("../data/raw/tweets_raw.csv")


def parse_stats(stats_value):
    """
    Convert a stats string like '(58, 1, 0, 0)'
    into views, likes, comments, retweets.
    """
    try:
        values = ast.literal_eval(stats_value)
        if isinstance(values, tuple) and len(values) == 4:
            return pd.Series(
                {
                    "views": values[0],
                    "likes": values[1],
                    "comments": values[2],
                    "retweets": values[3],
                }
            )
    except Exception:
        pass

    return pd.Series({"views": None, "likes": None, "comments": None, "retweets": None})


def clean_tweet(tweet):
    """
    Clean tweet text for analysis / deduplication.
    """
    if pd.isna(tweet):
        return ""

    tweet = str(tweet).lower()
    tweet = re.sub(r"https?://\S+|www\.\S+", "", tweet)  # remove URLs
    tweet = re.sub(r"@\w+", "", tweet)  # remove mentions
    tweet = re.sub(r"#", "", tweet)  # remove hashtag symbol only
    tweet = re.sub(r"[^\w\s]", "", tweet)  # remove punctuation/special chars
    tweet = " ".join(tweet.split())  # remove extra spaces
    return tweet


def extract_query_term(query):
    """
    Extract only the part before 'since' and remove all whitespace.
    Example:
        'betterhelp since:2026-02-01' -> 'betterhelp'
    """
    if pd.isna(query):
        return ""

    query = str(query)
    match = re.search(r"^(.*?)\s+since\b", query, flags=re.IGNORECASE)

    if match:
        extracted = match.group(1)
    else:
        extracted = query

    return re.sub(r"\s+", "", extracted).strip()


def is_english_tweet(text, min_prob=0.80, min_chars=20):
    """
    Keep only tweets that are likely English.
    min_prob is a practical threshold to reduce noisy short-text detections.
    """
    if not isinstance(text, str):
        return False

    text = text.strip()
    if len(text) < min_chars:
        return False

    try:
        langs = detect_langs(text)
        if not langs:
            return False

        top_lang = langs[0]
        return top_lang.lang == "en" and top_lang.prob >= min_prob
    except Exception:
        return False


def clean_csv(input_file, output_file):
    df = pd.read_csv(input_file)

    # Split stats column
    stats_df = df["stats"].apply(parse_stats)
    df = pd.concat([df.drop(columns=["stats"]), stats_df], axis=1)

    # Clean tweet text
    df["tweet"] = df["tweet"].apply(clean_tweet)

    # Keep only English tweets
    df = df[df["tweet"].apply(is_english_tweet)].copy()

    # Remove duplicates based on cleaned tweet text
    df = df.drop_duplicates(subset=["tweet"], keep="first")

    # Clean query text
    df["query"] = df["query"].apply(extract_query_term)

    # Reorder columns
    df = df[["tweet", "date", "views", "likes", "comments", "retweets", "query"]]

    # Save output
    df.to_csv(output_file, index=False)
    print(f"Cleaned CSV saved to: {output_file}")


clean_csv("../data/raw/tweets_raw.csv", "../data/cleaned/tweets_clean.csv")
