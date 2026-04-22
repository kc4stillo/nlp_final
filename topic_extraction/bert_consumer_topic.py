# %%
import pandas as pd
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
from umap import UMAP

# %%
pd.set_option("display.max_colwidth", None)
pd.set_option("display.max_columns", None)

# %%
df = pd.read_csv("../data/cleaned/combined.csv")

df["text"] = df["text"].fillna("").astype(str).str.lower().str.strip()
df["query"] = df["query"].fillna("").astype(str).str.lower().str.strip()

df = df[(df["text"] != "") & (df["query"] != "")].copy()
df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

df.head()


# %%
def get_brand_stopwords(query):
    brand_stopwords = {
        "lmnt": {"lmnt", "electrolyte", "electrolytes"},
        "ag1": {"ag1", "ag2", "agz", "gruns"},
        "betterhelp": {"betterhelp", "better", "help"},
        "magicspooncereal": {"magicspooncereal", "magic", "spoon"},
        "magic_spoon": {"magic_spoon", "magic", "spoon"},
    }
    return brand_stopwords.get(str(query).lower(), set())


# %%
# one embedding model reused for all groups
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# %%
all_topic_info = []
all_assignments = []
models = {}

for query_name, df_query in df.groupby("query"):
    docs = df_query["text"].tolist()

    if len(docs) < 10:
        print(f"Skipping {query_name}: only {len(docs)} docs")
        continue

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
        "going",
        "say",
        "said",
        "make",
        "made",
        "thing",
        "things",
        "lot",
        "little",
        "try",
        "using",
        "use",
        "used",
    }
    stop_words = list(custom_stopwords.union(get_brand_stopwords(query_name)))

    vectorizer_model = CountVectorizer(
        stop_words=stop_words,
        min_df=2,
        ngram_range=(1, 2),
    )

    umap_model = UMAP(
        n_neighbors=10,
        n_components=5,
        min_dist=0.0,
        metric="cosine",
        random_state=42,
    )

    topic_model = BERTopic(
        language="english",
        embedding_model=embedding_model,
        vectorizer_model=vectorizer_model,
        umap_model=umap_model,
        min_topic_size=8,
        top_n_words=10,
        calculate_probabilities=True,
        verbose=False,
    )

    # precompute embeddings for faster iteration
    embeddings = embedding_model.encode(docs, show_progress_bar=True)

    topics, probs = topic_model.fit_transform(docs, embeddings)

    # topic summary
    info = topic_model.get_topic_info().copy()
    info["query"] = query_name
    all_topic_info.append(info)

    # per-document assignment
    assignments = df_query.copy()
    assignments["bertopic_topic"] = topics

    if probs is not None:
        # if probs is 2D, use row max; if 1D, use directly
        try:
            assignments["topic_prob"] = probs.max(axis=1)
        except Exception:
            assignments["topic_prob"] = probs
    else:
        assignments["topic_prob"] = None

    all_assignments.append(assignments)
    models[query_name] = topic_model

# %%
topic_info_df = pd.concat(all_topic_info, ignore_index=True)
assignments_df = pd.concat(all_assignments, ignore_index=True)

# %%
# cleaner topic summary: keep the most useful columns
topic_summary = topic_info_df.copy()

keep_cols = [
    c
    for c in ["query", "Topic", "Count", "Name", "Representation"]
    if c in topic_summary.columns
]
topic_summary = topic_summary[keep_cols]

# remove outlier topic -1 if you only want "real" topics
topic_summary_clean = topic_summary[topic_summary["Topic"] != -1].copy()

topic_summary_clean
