# %%
import re
import pandas as pd
import ast
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
            return pd.Series({
                "views": values[0],
                "likes": values[1],
                "comments": values[2],
                "retweets": values[3]
            })
    except Exception:
        pass

    return pd.Series({
        "views": None,
        "likes": None,
        "comments": None,
        "retweets": None
    })


def clean_tweet(tweet):
    """
    Clean tweet text for analysis / deduplication.
    """
    if pd.isna(tweet):
        return ""

    tweet = str(tweet).lower()
    tweet = re.sub(r'https?://\S+|www\.\S+', '', tweet)   # remove URLs
    tweet = re.sub(r'@\w+', '', tweet)                    # remove mentions
    tweet = re.sub(r'#', '', tweet)                       # remove hashtag symbol only
    tweet = re.sub(r'[^\w\s]', '', tweet)                 # remove punctuation/special chars
    tweet = " ".join(tweet.split())                       # remove extra spaces
    return tweet


def clean_csv(input_file, output_file):
    df = pd.read_csv(input_file)

    # Split stats column
    stats_df = df["stats"].apply(parse_stats)
    df = pd.concat([df.drop(columns=["stats"]), stats_df], axis=1)

    # Clean tweet text
    df["tweet"] = df["tweet"].apply(clean_tweet)

    # Remove duplicates based on cleaned tweet text
    df = df.drop_duplicates(subset=["tweet"], keep="first")

    # Reorder columns
    df = df[[
        "tweet",
        "date",
        "views",
        "likes",
        "comments",
        "retweets",
        "query"
    ]]

    # Save output
    df.to_csv(output_file, index=False)
    print(f"Cleaned CSV saved to: {output_file}")

clean_csv("../data/raw/tweets_raw.csv", "../data/cleaned/tweets_clean.csv")