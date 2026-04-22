# %%
import re

import numpy as np
import pandas as pd
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

# %%
pd.set_option("display.max_colwidth", None)
pd.set_option("display.max_columns", None)

# %%
yt = pd.read_csv("../data/cleaned/yt_cleaned.csv")

# basic cleanup
yt["transcript"] = yt["transcript"].fillna("").astype(str).str.lower().str.strip()
yt["lda"] = yt["lda"].fillna("").astype(str).str.lower().str.strip()
yt["topic"] = yt["topic"].fillna("").astype(str).str.lower().str.strip()

yt = yt[(yt["transcript"] != "") & (yt["lda"] != "") & (yt["topic"] != "")].copy()

# optional dedupe
# dedupe on original text so you keep one real document, while preserving lda text
yt = yt.drop_duplicates(subset=["transcript"], keep="first").reset_index(drop=True)

yt.head()


# %%
def normalize_query_words(query: str):
    """
    Split topic/query into words so brand names don't dominate their own topics.
    """
    query = str(query).lower()
    query = re.sub(r"[^a-z0-9\s]", " ", query)
    return set(query.split())


def get_brand_stopwords(query):
    """
    Remove brand words so topics focus on themes, not brand repetition.
    """
    brand_stopwords = {
        "lmnt": {"lmnt"},
        "ag1": {"ag1", "athletic", "greens"},
        "betterhelp": {"betterhelp", "better", "help"},
        "magicspooncereal": {"magicspooncereal", "magic", "spoon"},
        "magic spoon": {"magic", "spoon"},
    }
    return brand_stopwords.get(str(query).lower(), set())


def extract_topics_for_topic(
    df_topic,
    topic_name,
    text_col="lda",
    n_topics=2,
    n_top_words=10,
    min_df=2,
    max_df=0.95,
    random_state=42,
):
    """
    Fit LDA for one topic group and return:
      - topic keywords
      - transcript-topic assignments
      - fitted lda/vectorizer

    text_col should be the LDA-ready text column.
    """
    docs = df_topic[text_col].dropna().astype(str)
    docs = docs[docs.str.strip() != ""]

    if len(docs) < 2:
        print(f"Skipping '{topic_name}' (not enough docs)")
        return None, None, None, None

    query_stopwords = normalize_query_words(topic_name)
    brand_stopwords = get_brand_stopwords(topic_name)

    custom_stopwords = {
        "just",
        "like",
        "im",
        "ive",
        "dont",
        "youre",
        "people",
        "really",
        "good",
        "great",
        "know",
        "think",
        "want",
        "today",
        "going",
        "now",
        "say",
        "said",
        "make",
        "made",
        "thing",
        "things",
        "way",
        "lot",
        "little",
        "thank",
        "thanks",
        "video",
        "videos",
        "channel",
    }

    stop_words = list(
        set(ENGLISH_STOP_WORDS)
        .union(query_stopwords)
        .union(brand_stopwords)
        .union(custom_stopwords)
    )

    vectorizer = CountVectorizer(
        stop_words=stop_words,
        min_df=min_df,
        max_df=max_df,
        ngram_range=(1, 2),
    )

    X = vectorizer.fit_transform(docs)

    if X.shape[0] == 0 or X.shape[1] < n_topics:
        print(f"Skipping '{topic_name}' (vocab too small: {X.shape[1]} terms)")
        return None, None, None, None

    lda = LatentDirichletAllocation(
        n_components=n_topics,
        random_state=random_state,
        learning_method="batch",
    )

    doc_topic = lda.fit_transform(X)
    feature_names = np.array(vectorizer.get_feature_names_out())

    topic_rows = []
    for topic_idx, topic_weights in enumerate(lda.components_):
        top_idx = topic_weights.argsort()[::-1][:n_top_words]
        top_terms = feature_names[top_idx]

        topic_rows.append(
            {
                "topic_group": topic_name,
                "topic": topic_idx,
                "top_words": ", ".join(top_terms),
            }
        )

    topics_df = pd.DataFrame(topic_rows)

    # keep original transcript alongside lda text for future BERT / BERTopic work
    assignments = df_topic.loc[docs.index].copy()
    assignments["dominant_topic"] = doc_topic.argmax(axis=1)
    assignments["topic_score"] = doc_topic.max(axis=1)

    return topics_df, assignments, lda, vectorizer


# %%
all_topics = []
all_assignments = []
models = {}

for topic_name, df_topic in yt.groupby("topic"):
    topics_df, assignments_df, lda_model, vec = extract_topics_for_topic(
        df_topic,
        topic_name=topic_name,
        text_col="lda",  # <-- use lda column, not transcript
        n_topics=2,
        n_top_words=10,
    )

    if topics_df is not None:
        all_topics.append(topics_df)
        all_assignments.append(assignments_df)
        models[topic_name] = {"lda": lda_model, "vectorizer": vec}

yt_topics_by_group = pd.concat(all_topics, ignore_index=True)
yt_topic_assignments = pd.concat(all_assignments, ignore_index=True)

yt_topics_by_group
