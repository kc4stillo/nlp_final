# %%
import csv
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from utilities import random_long_wait, random_short_wait

# %%
PREFERRED_TIME_ZONE = ZoneInfo("America/Chicago")

###### EARLIER DATE
START_DATE = datetime(2026, 2, 7, tzinfo=PREFERRED_TIME_ZONE)
start_date_text = START_DATE.strftime("%Y-%m-%d")

###### LATER DATE
END_DATE = datetime(2026, 3, 8, tzinfo=PREFERRED_TIME_ZONE)
end_date_text = END_DATE.strftime("%Y-%m-%d")


# %%
def main(p):
    browser, context, page = open_page(p)

    try:
        queries = txt_to_list()
        for query in queries:
            search_query = f"{query} since:{start_date_text} until:{end_date_text}"

            random_short_wait()

            page = search(page, search_query)

            random_short_wait()

            # scrape will write tweets immediately for `query`
            print(scrape(page, START_DATE, END_DATE, PREFERRED_TIME_ZONE, query))

            print(f"Done scraping query: {query}")

            # brief rest between queries
            random_long_wait()
    finally:
        # ensure browser closes even if something errors
        try:
            context.close()
            browser.close()
        except Exception:
            pass

    print("DONE!")


def txt_to_list():
    """read queries from file (one per non-empty line)"""
    file_path = "../ref/queries.txt"

    queries = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()
            queries.append(stripped_line)

    return queries


def open_page(p):
    browser = p.chromium.launch(headless=False)

    context = browser.new_context()
    page = context.new_page()

    page.goto("http://localhost:8080/")

    return browser, context, page


def search(page, query):
    page.locator('input[name="q"]').click()
    page.locator('input[name="q"]').fill(query)
    page.keyboard.press("Enter")

    return page


def scrape(
    page,
    start_date,
    end_date,
    time_zone,
    query,
    file_name: str = "tweets_raw.csv",
):
    content_list = []
    i = 1

    failed_reads = 0  # for tweet_time is None
    consecutive_duplicates = 0  # for duplicate/stall scrolling

    # while True:
    return read_tweet_content(page, content_list, time_zone)

    # if tweet_time is None:
    #     print("No tweet timestamp found; scrolling and retrying...")
    #     scroll_to_next_tweet(page)
    #     failed_reads += 1
    #     if failed_reads >= 8:
    #         print("Too many failed reads — aborting this query.")
    #         break
    #     continue
    # else:
    #     failed_reads = 0  # ONLY reset failed-reads here

    # # stop when older than start_date
    # if tweet_time < start_date:
    #     if i == 1 and not content_list:
    #         print("NO TWEETS IN THE TIME FRAME")
    #     else:
    #         print("Reached tweets older than start_date; stopping scrape.")
    #     break

    # # skip tweets newer than end_date
    # if tweet_time > end_date:
    #     print("Found tweet newer than end_date — skipping and scrolling.")
    #     scroll_to_next_tweet(page)
    #     continue

    # if new_tweet_appended and tweet_data is not None:
    #     consecutive_duplicates = 0  # reset ONLY when we got a new tweet

    #     print("------------------------------------------")
    #     print("TWEET #", i)
    #     print("APPENDED TWEET FROM TIME", tweet_time)
    #     print("CURRENT TWEET CONTENT:", content_list[-1][0][:140])  # preview

    #     try:
    #         write_single_tweet_to_csv(tweet_data, query, file_name)
    #     except Exception as e:
    #         print("Error writing tweet to CSV:", e)

    #     i += 1
    #     scroll_to_next_tweet(page)
    # else:
    #     # duplicate / stall
    #     consecutive_duplicates += 1
    #     print("SCROLLING, TWEET WAS DUPLICATE OR ALREADY COLLECTED")

    #     if consecutive_duplicates >= 30:
    #         print(
    #             "No new tweets after 30 duplicate/stall scrolls — stopping this query."
    #         )
    #         break

    #     scroll_to_next_tweet(page)

    return content_list


def read_tweet_content(page, content_list, time_zone):
    """read all tweets within page"""

    items = page.locator(".timeline-item").all()

    results = []
    for item in items:
        text = item.locator(".tweet-content.media-body").inner_text()
        date = item.locator(".tweet-date a").get_attribute("title")

        results.append((text, date))
        content_list.append((text, date))

    return results


def scroll_to_next_tweet(page):
    tweet_locator = page.locator('article[data-testid="tweet"]').first
    try:
        height = tweet_locator.evaluate("element => element.offsetHeight")
        if not isinstance(height, (int, float)) or height <= 0:
            height = 800
    except Exception:
        height = 800

    print("SCROLLING:", height, "PIXELS")
    page.mouse.wheel(0, height)
    random_short_wait()


def write_single_tweet_to_csv(tweet_data, query, file_name):
    """
    Append a single tweet row to CSV.
    Writes the header if file does not exist or is empty.
    Serializes tweet_analytics to JSON to keep CSV safe.
    """
    folder_path = "../../data/raw"
    file_path = os.path.join(folder_path, file_name)

    # ensure parent folder exists first
    os.makedirs(folder_path, exist_ok=True)

    # now check if file has content (not just existence)
    file_has_content = os.path.isfile(file_path) and os.path.getsize(file_path) > 0

    tweet_text, tweet_analytics, tweet_datetime = tweet_data

    # sanitize text
    cleaned_tweet_text = tweet_text.replace("\r", " ").replace("\n", " ").strip()

    # turn analytics into a JSON string to store as a single CSV cell
    try:
        tweet_analytics_json = json.dumps(tweet_analytics, ensure_ascii=False)
    except Exception:
        tweet_analytics_json = str(tweet_analytics)

    # format datetime
    try:
        formatted_date = tweet_datetime.strftime("%Y-%m-%d %H:%M:%S %z")
    except Exception:
        formatted_date = str(tweet_datetime)

    # write row
    with open(file_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_has_content:
            # write header exactly once (if file is new or empty)
            writer.writerow(["tweet_text", "tweet_analytics", "date", "query"])

        writer.writerow(
            [cleaned_tweet_text, tweet_analytics_json, formatted_date, query]
        )


if __name__ == "__main__":
    with sync_playwright() as p:
        main(p)
