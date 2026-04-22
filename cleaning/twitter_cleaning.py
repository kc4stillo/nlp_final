# %%
import ast
import re

import nltk
import pandas as pd
from langdetect import DetectorFactory, detect_langs
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# make langdetect deterministic
DetectorFactory.seed = 0

# download nltk resources once
nltk.download("stopwords")
nltk.download("wordnet")
nltk.download("omw-1.4")

# %%
tweets_raw = pd.read_csv("../data/raw/tweets_raw.csv")

STOP_WORDS = set(stopwords.words("english"))
LEMMATIZER = WordNetLemmatizer()

# optional extra stopwords for tweet / social media text
EXTRA_STOPWORDS = {
    "im",
    "ive",
    "id",
    "youre",
    "youve",
    "theyre",
    "thats",
    "theres",
    "cant",
    "couldnt",
    "didnt",
    "doesnt",
    "dont",
    "isnt",
    "wasnt",
    "werent",
    "wont",
    "wouldnt",
    "rt",
    "amp",
}
STOP_WORDS = STOP_WORDS.union(EXTRA_STOPWORDS)


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
    Keeps plain lowercase text before LDA-specific processing.
    """
    if pd.isna(tweet):
        return ""

    tweet = str(tweet).lower()
    tweet = re.sub(r"https?://\S+|www\.\S+", " ", tweet)  # remove URLs
    tweet = re.sub(r"@\w+", " ", tweet)  # remove mentions
    tweet = re.sub(r"#", "", tweet)  # remove hashtag symbol only
    tweet = re.sub(r"[^\w\s]", " ", tweet)  # remove punctuation/special chars
    tweet = re.sub(r"\s+", " ", tweet).strip()  # remove extra spaces
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

    return re.sub(r"\s+", "", extracted).strip().lower()


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


def build_query_stopwords(query_value):
    """
    Build a set of words from the query/product term so they can be removed
    from the tweet for topic modeling.
    Example:
        'betterhelp' -> {'betterhelp'}
        'magicspoon' -> {'magicspoon'}
    """
    if not isinstance(query_value, str):
        return set()

    parts = re.findall(r"[a-z]+", query_value.lower())
    return set(parts)


def preprocess_for_lda(text, query_value):
    """
    Create an LDA-ready version of tweet text:
    - tokenize
    - remove numbers
    - remove short tokens
    - remove stopwords
    - remove product/query words
    - lemmatize
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    query_words = build_query_stopwords(query_value)

    tokens = re.findall(r"\b[a-z]+\b", text.lower())

    processed_tokens = []
    for token in tokens:
        if token in STOP_WORDS:
            continue
        if token in query_words:
            continue
        if len(token) < 3:
            continue

        lemma = LEMMATIZER.lemmatize(token)

        if lemma in STOP_WORDS:
            continue
        if lemma in query_words:
            continue
        if len(lemma) < 3:
            continue

        processed_tokens.append(lemma)

    return " ".join(processed_tokens)


def clean_csv(input_file, output_file):
    df = pd.read_csv(input_file)

    # Split stats column
    stats_df = df["stats"].apply(parse_stats)
    df = pd.concat([df.drop(columns=["stats"]), stats_df], axis=1)

    # Clean query text first so we can use it during LDA preprocessing
    df["query"] = df["query"].apply(extract_query_term)

    # Clean tweet text
    df["tweet"] = df["tweet"].apply(clean_tweet)

    # Keep only English tweets
    df = df[df["tweet"].apply(is_english_tweet)].copy()

    # Remove duplicates based on cleaned tweet text
    df = df.drop_duplicates(subset=["tweet"], keep="first")

    # Create LDA-ready text column
    df["lda"] = df.apply(
        lambda row: preprocess_for_lda(row["tweet"], row["query"]), axis=1
    )

    # Remove rows that became empty after LDA preprocessing
    df = df[df["lda"].str.strip() != ""].copy()

    # Reorder columns
    df = df[
        [
            "tweet",
            "lda",
            "date",
            "views",
            "likes",
            "comments",
            "retweets",
            "query",
        ]
    ]

    # Save output
    df.to_csv(output_file, index=False)
    print(f"Cleaned CSV saved to: {output_file}")


clean_csv("../data/raw/tweets_raw.csv", "../data/cleaned/tweets_clean.csv")
