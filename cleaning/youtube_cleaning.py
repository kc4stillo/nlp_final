import re

import nltk
import pandas as pd
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# -------------------------------------------------------------------
# NLTK SETUP
# -------------------------------------------------------------------
nltk.download("stopwords")
nltk.download("wordnet")
nltk.download("omw-1.4")

STOP_WORDS = set(stopwords.words("english"))
LEMMATIZER = WordNetLemmatizer()

# extra filler words common in transcripts / spoken language
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
    "uh",
    "um",
    "like",
    "yeah",
    "okay",
    "ok",
    "really",
    "actually",
    "kind",
    "sort",
    "gonna",
    "wanna",
}
STOP_WORDS = STOP_WORDS.union(EXTRA_STOPWORDS)

# -------------------------------------------------------------------
# TOPIC-SPECIFIC ALIASES
# -------------------------------------------------------------------
# Add more brand aliases here as needed
topic_aliases = {
    "ag1": [r"ag1", r"athletic greens"],
    "lmnt": [r"lmnt", r"element"],
    "betterhelp": [r"betterhelp", r"better help"],
    "magicspoon": [r"magicspoon", r"magic spoon"],
    "magic spoon": [r"magicspoon", r"magic spoon"],
}


def build_topic_stopwords(topic):
    """
    Build a set of topic/brand words to remove during LDA preprocessing.
    Pulls from topic_aliases if available, otherwise falls back to the topic text itself.
    """
    if pd.isna(topic):
        return set()

    topic = str(topic).lower().strip()
    alias_patterns = topic_aliases.get(topic, [topic])

    topic_words = set()
    for alias in alias_patterns:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", alias.lower())
        parts = re.findall(r"\b[a-z0-9]+\b", cleaned)
        topic_words.update(parts)

    return topic_words


def clean_youtube_transcript(text, topic=None, remove_brand_terms=False):
    """
    Clean transcript text for readability / storage.
    """
    if pd.isna(text):
        return ""

    text = str(text)

    # normalize apostrophes / dashes
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
    )

    # lowercase
    text = text.lower()

    # remove urls
    text = re.sub(r"http\S+|www\.\S+", " ", text)

    # remove timestamps like 0:30 or 12:45 or 1:02:15
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", text)

    # remove bracketed stage directions / captions
    text = re.sub(r"\[(.*?)\]|\((music|applause|laughter|sponsor)\)", " ", text)

    # remove common sponsor boilerplate phrases
    boilerplate_patterns = [
        r"\bthis video is sponsored by\b",
        r"\bthis episode is sponsored by\b",
        r"\bthis portion of the video is sponsored by\b",
        r"\bthis podcast is sponsored by\b",
        r"\bbrought to you by\b",
        r"\bthank you to .*? for sponsoring\b",
        r"\bthanks to .*? for sponsoring\b",
        r"\bpartnered with\b",
        r"\bin partnership with\b",
        r"\bpaid partnership with\b",
        r"\bspecial thanks to .*? for sponsoring\b",
    ]
    for pattern in boilerplate_patterns:
        text = re.sub(pattern, " ", text)

    # remove topic-specific brand words from each transcript
    if remove_brand_terms and topic is not None:
        topic = str(topic).lower().strip()
        patterns = topic_aliases.get(topic, [re.escape(topic)])

        for p in patterns:
            text = re.sub(rf"\b{p}\b", " ", text, flags=re.IGNORECASE)

    # collapse repeated words: "ever ever ever" -> "ever"
    text = re.sub(r"\b(\w+)( \1\b)+", r"\1", text)

    # remove non-letter chars except spaces
    text = re.sub(r"[^a-z\s]", " ", text)

    # remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def preprocess_for_lda(text, topic):
    """
    Create an LDA-ready version of transcript text:
    - tokenize
    - remove stopwords
    - remove topic words
    - remove short tokens
    - lemmatize
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    topic_words = build_topic_stopwords(topic)

    tokens = re.findall(r"\b[a-z]+\b", text.lower())

    processed_tokens = []
    for token in tokens:
        if token in STOP_WORDS:
            continue
        if token in topic_words:
            continue
        if len(token) < 3:
            continue

        lemma = LEMMATIZER.lemmatize(token)

        if lemma in STOP_WORDS:
            continue
        if lemma in topic_words:
            continue
        if len(lemma) < 3:
            continue

        processed_tokens.append(lemma)

    return " ".join(processed_tokens)


yt = pd.read_csv("../data/raw/youtube/youtube_raw.csv")

# Clean transcripts while removing each row's topic word/aliases
yt["transcript"] = yt.apply(
    lambda row: clean_youtube_transcript(
        row["transcript"], topic=row["topic"], remove_brand_terms=True
    ),
    axis=1,
)

# Build LDA-ready column
yt["lda"] = yt.apply(
    lambda row: preprocess_for_lda(row["transcript"], row["topic"]),
    axis=1,
)

# Drop rows where cleaned transcript or lda text is empty
yt = yt[yt["transcript"].str.strip() != ""].copy()
yt = yt[yt["lda"].str.strip() != ""].copy()

yt.to_csv("../data/cleaned/yt_cleaned.csv", index=False)
print("Cleaned CSV saved to: ../data/cleaned/yt_cleaned.csv")
print(f"Rows kept: {len(yt)}")
