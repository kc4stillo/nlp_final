# %%
import csv
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from utilities import random_long_wait

# %%
PREFERRED_TIME_ZONE = ZoneInfo("America/Chicago")

###### LESS RECENT DATE
START_DATE = datetime(2026, 4, 1, tzinfo=PREFERRED_TIME_ZONE)
start_date_text = START_DATE.strftime("%Y-%m-%d")

###### MOST RECENT DATE
# END_DATE = datetime(2026, 3, 8, tzinfo=PREFERRED_TIME_ZONE)
# # END_DATE = datetime.now(PREFERRED_TIME_ZONE)
# end_date_text = END_DATE.strftime("%Y-%m-%d")


# %%
def main(p):
    browser, context, page = open_page(p)

    queries = txt_to_list()
    for query in queries:
        search_query = f"{query} since:{start_date_text}"
        page = search(page, search_query)

        random_long_wait()

        scrape(page)
        print(f"Done scraping query: {query}")

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
        tweet_content = read_tweet_content(page, content_list)
        write_to_csv(tweet_content)
        page = scroll_and_click(page)
        random_long_wait()

    return content_list


def read_tweet_content(page, content_list):
    """Read all tweets within page."""
    timeline_items = page.locator(".timeline-item")

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


def write_to_csv(tweets, filename="tweets_raw"):
    """
    write (tweet_content, date) tuples to a csv file.
    """
    file_exists = os.path.isfile(f"../data/{filename}")

    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["tweet_content", "date"])

        writer.writerows(tweets)


if __name__ == "__main__":
    with sync_playwright() as p:
        main(p)
