import os
import pandas as pd
from transformers import pipeline

INPUT_FILE = "/Users/riyalouis/Documents/GitHub/nlp_final/data/cleaned/tweets_clean.csv"
OUTPUT_FILE = "all_tweets_sentiment.csv"

analyzer = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

def main():
    df = load_data(INPUT_FILE)
    df = analyze_sentiment(df)
    summary = compute_summary(df)
    print_summary(summary)
    save_output(df, OUTPUT_FILE)
    print(f"\nDONE! Results saved to: {OUTPUT_FILE}")

def load_data(file_path):
    df = pd.read_csv(file_path)
    print(f"Loaded {len(df)} rows from {file_path}")
    print(f"Topics: {df['topic'].unique().tolist()}\n")
    return df

def score_text(text):
    """Run Transformer on text. Returns label and confidence score."""
    if not isinstance(text, str) or text.strip() == "":
        return None, None
    result = analyzer(text[:1500])[0] 
    return result["label"], result["score"]

def analyze_sentiment(df):
    results = df["tweet"].apply(lambda text: pd.Series(score_text(text)))
    results.columns = ["sentiment", "confidence"]

    df = pd.concat([df, results], axis=1)

    df["sentiment_score"] = df.apply(
        lambda row: row["confidence"] if row["sentiment"] == "POSITIVE" else -row["confidence"], 
        axis=1
    )

    return df

def compute_summary(df):
    """Compute per-topic and overall sentiment summaries."""
    summaries = {}
    scored = df.dropna(subset=["sentiment_score"])

    # Helper to determine overall label from mean score
    def get_label(val):
        return "POSITIVE" if val > 0 else "NEGATIVE"

    # Overall
    summaries["overall"] = {
        "total": len(df),
        "scored": len(scored),
        "avg_score": round(scored["sentiment_score"].mean(), 4),
        "label": get_label(scored["sentiment_score"].mean()),
        "positive": (scored["sentiment"] == "POSITIVE").sum(),
        "negative": (scored["sentiment"] == "NEGATIVE").sum(),
    }

    # Per topic
    summaries["by_topic"] = {}
    for topic, group in scored.groupby("topic"):
        summaries["by_topic"][topic] = {
            "total": len(group),
            "avg_score": round(group["sentiment_score"].mean(), 4),
            "label": get_label(group["sentiment_score"].mean()),
            "positive": (group["sentiment"] == "POSITIVE").sum(),
            "negative": (group["sentiment"] == "NEGATIVE").sum(),
        }

    return summaries

def print_summary(summary):
    o = summary["overall"]
    print("=" * 60)
    print("OVERALL TRANSFORMER SENTIMENT SUMMARY")
    print(f"  Total rows scored : {o['scored']} / {o['total']}")
    print(f"  Avg sentiment score: {o['avg_score']:+.4f}  ({o['label']})")
    print(f"  Positive          : {o['positive']}")
    print(f"  Negative          : {o['negative']}")
    print("=" * 60)

    print("\nSENTIMENT BY TOPIC")
    for topic, stats in summary["by_topic"].items():
        print(f"\n  {topic}")
        print(f"    Rows        : {stats['total']}")
        print(f"    Avg score   : {stats['avg_score']:+.4f}  ({stats['label']})")
        print(f"    Positive    : {stats['positive']}")
        print(f"    Negative    : {stats['negative']}")
    print()

def save_output(df, output_path):
    """Save the sentiment-annotated dataframe to CSV."""
    if "sentiment_score" in df.columns:
        df["sentiment_score"] = df["sentiment_score"].round(4)
    if "confidence" in df.columns:
        df["confidence"] = df["confidence"].round(4)

    df.to_csv(output_path, index=False, encoding="utf-8")

if __name__ == "__main__":
    main()