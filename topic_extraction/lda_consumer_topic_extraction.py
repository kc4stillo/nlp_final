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
tweets = pd.read_csv("../data/cleaned/tweets_clean.csv")
reddit = pd.read_csv("../data/cleaned/reddit_clean.csv")

tweets.head()
# tweet    lda    date    views    likes    comments    retweets    query

reddit.head()
# reddit    lda    topic    score

# keep tweets that are somewhat relevant
tweets = tweets[(tweets["comments"] > 1) | (tweets["views"] > 300)].copy()

# clean original tweet text
tweets["tweet"] = tweets["tweet"].fillna("").astype(str).str.lower().str.strip()
tweets["lda"] = tweets["lda"].fillna("").astype(str).str.lower().str.strip()
tweets["query"] = tweets["query"].fillna("").astype(str).str.lower().str.strip()

tweets = tweets[(tweets["tweet"] != "") & (tweets["lda"] != "")]

# clean original reddit text
reddit["reddit"] = reddit["reddit"].fillna("").astype(str).str.lower().str.strip()
reddit["lda"] = reddit["lda"].fillna("").astype(str).str.lower().str.strip()
reddit["topic"] = reddit["topic"].fillna("").astype(str).str.lower().str.strip()

reddit = reddit[(reddit["reddit"] != "") & (reddit["lda"] != "")]

# map reddit topic names to twitter query names
topic_map = {
    "ag1 powder": "ag1",
    "betterhelp therapy": "betterhelp",
    "magic spoon": "magicspooncereal",
    "lmnt electrolytes": "lmnt",
}

reddit = reddit[reddit["topic"].isin(topic_map.keys())].copy()
reddit["query"] = reddit["topic"].map(topic_map).str.lower().str.strip()

# standardize columns so they can be concatenated
# text = original cleaned text for future BERT / BERTopic work
# lda  = more aggressively preprocessed text for LDA
tweets_small = (
    tweets[["tweet", "lda", "query"]].copy().rename(columns={"tweet": "text"})
)
reddit_small = (
    reddit[["reddit", "lda", "query"]].copy().rename(columns={"reddit": "text"})
)

# combine twitter + reddit into one corpus
combined = pd.concat([tweets_small, reddit_small], ignore_index=True)

# optional dedupe:
# dedupe by original text so you preserve one copy of each real document
combined = combined.drop_duplicates(subset=["text"], keep="first").reset_index(
    drop=True
)

combined.head()

combined.to_csv("../data/cleaned/combined.csv", index=False)


# %%
def normalize_query_words(query: str):
    """
    Split query into words so brand names don't dominate their own topics.
    Example: 'magic spoon' -> {'magic', 'spoon'}
    """
    query = str(query).lower()
    query = re.sub(r"[^a-z0-9\s]", " ", query)
    return set(query.split())


def extract_topics_for_query(
    df_query,
    query_name,
    text_col="lda",
    n_topics=5,
    n_top_words=10,
    min_df=2,
    max_df=0.9,
    random_state=42,
):
    """
    Fit LDA for one query group and return:
      - topic keywords
      - doc-topic assignments
      - fitted lda/vectorizer

    text_col should be the LDA-ready text column.
    """
    docs = df_query[text_col].dropna().astype(str)
    docs = docs[docs.str.strip() != ""]

    query_stopwords = normalize_query_words(query_name)
    stop_words = list(set(ENGLISH_STOP_WORDS).union(query_stopwords))

    vectorizer = CountVectorizer(
        stop_words=stop_words,
        min_df=min_df,
        max_df=max_df,
        ngram_range=(1, 2),
    )

    X = vectorizer.fit_transform(docs)

    if X.shape[0] == 0 or X.shape[1] < n_topics:
        print(f"Skipping '{query_name}' (vocab too small: {X.shape[1]} terms)")
        return None, None, None, None

    lda = LatentDirichletAllocation(
        n_components=n_topics,
        random_state=random_state,
        learning_method="batch",
    )

    doc_topic = lda.fit_transform(X)
    feature_names = np.array(vectorizer.get_feature_names_out())

    # topic -> top words
    topic_rows = []
    for topic_idx, topic_weights in enumerate(lda.components_):
        top_idx = topic_weights.argsort()[::-1][:n_top_words]
        top_terms = feature_names[top_idx]

        topic_rows.append(
            {
                "query": query_name,
                "topic": topic_idx,
                "top_words": ", ".join(top_terms),
            }
        )

    topics_df = pd.DataFrame(topic_rows)

    # document -> dominant topic
    # keep original text alongside lda text for later inspection
    assignments = df_query.loc[docs.index].copy()
    assignments["dominant_topic"] = doc_topic.argmax(axis=1)
    assignments["topic_score"] = doc_topic.max(axis=1)

    return topics_df, assignments, lda, vectorizer


# %%
all_topics = []
all_assignments = []
models = {}

for query, df_query in combined.groupby("query"):
    topics_df, assignments_df, lda_model, vec = extract_topics_for_query(
        df_query,
        query_name=query,
        text_col="lda",  # <-- use lda column, not text
        n_topics=2,
        n_top_words=10,
    )

    if topics_df is not None:
        all_topics.append(topics_df)
        all_assignments.append(assignments_df)
        models[query] = {"lda": lda_model, "vectorizer": vec}

topics_by_query = pd.concat(all_topics, ignore_index=True)
doc_topic_assignments = pd.concat(all_assignments, ignore_index=True)

topics_by_query

# %%
# doc_topic_assignments
