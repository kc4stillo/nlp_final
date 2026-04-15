# %%
import csv
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from utilities import random_long_wait, random_short_wait

# %%
PREFERRED_TIME_ZONE = ZoneInfo("America/Chicago")

###### LESS RECENT DATE
START_DATE = datetime(2026, 2, 8, tzinfo=PREFERRED_TIME_ZONE)
start_date_text = START_DATE.strftime("%Y-%m-%d")

###### MOST RECENT DATE
END_DATE = datetime(2026, 3, 8, tzinfo=PREFERRED_TIME_ZONE)
# END_DATE = datetime.now(PREFERRED_TIME_ZONE)
end_date_text = END_DATE.strftime("%Y-%m-%d")


# %%
def main(p):
    browser, context, page = open_page(p)

    queries = txt_to_list()
    for query in queries:
        search_query = f"{query} since:{start_date_text}"
        # \ until:{end_date_text}"
        page = search(page, search_query)

        random_long_wait()
        # scrape will write tweets immediately for `query`

        scrape(page)
        print(f"Done scraping query: {query}")

        # brief rest between queries
        random_long_wait()


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
    file_name: str = "tweets_raw.csv",
):
    content_list = []

    while True:
        if page.locator("h2.timeline-end").count():
            print("NO MORE TWEETS, BREAKING NOW")
            break
        read_tweet_content(page, content_list)
        random_short_wait()
        page = scroll_and_click(page)
        random_long_wait()
        random_long_wait()
        random_long_wait()

    return content_list


def read_tweet_content(page, content_list):
    """Read all tweets within page."""
    timeline_items = page.locator(".timeline-item")

    # wait
    timeline_items.first.wait_for(state="attached")

    results = []
    count = timeline_items.count()

    for i in range(count):
        item = timeline_items.nth(i)

        text_locator = item.locator(".tweet-content.media-body")
        date_locator = item.locator(".tweet-date a")

        # skip items that arent tweets
        if text_locator.count() == 0 or date_locator.count() == 0:
            continue

        text = text_locator.first.text_content()
        date_str = date_locator.first.get_attribute("title")

        if not text or not date_str:
            continue

        text = text.strip()

        date = (
            datetime.strptime(date_str.strip(), "%b %d, %Y · %I:%M %p UTC")
            .replace(tzinfo=timezone.utc)
            .astimezone(PREFERRED_TIME_ZONE)
        )

        results.append((text, date))
        content_list.append((text, date))

    return results


def scroll_and_click(page):
    page.mouse.wheel(0, 5000)

    load_more = page.get_by_role("link", name="Load more")

    if load_more.count() > 0:
        load_more.first.click()

    return page


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
