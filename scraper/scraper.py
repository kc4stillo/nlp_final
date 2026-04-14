# %%
import csv
import json
import os
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from html_parser import extract_analytics, extract_time, extract_tweet_text
from playwright.sync_api import TimeoutError, sync_playwright

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
            page = search(page, search_query)

            # scrape will write tweets immediately for `query`
            scrape(page, START_DATE, END_DATE, PREFERRED_TIME_ZONE, query)
            print(f"Done scraping query: {query}")

            # brief rest between queries
            time.sleep(10)
    finally:
        # ensure browser closes even if something errors
        try:
            context.close()
            browser.close()
        except Exception:
            pass

    print("DONE!")


def random_short_wait(min_seconds: int = 1, max_seconds: int = 2):
    """sleep a random short interval"""
    time.sleep(random.randint(min_seconds, max_seconds))


def txt_to_list():
    """read queries from file (one per non-empty line)"""
    file_path = "../ref/queries.txt"

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Queries file not found at: {file_path}")

    queries = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()
            if stripped_line:
                queries.append(stripped_line)
    return queries


def open_page(p):
    browser = p.chromium.launch(headless=False)

    context = browser.new_context()
    page = context.new_page()
    page.goto("nitter.net")

    return browser, context, page


# what??
def search(page, query):
    random_short_wait()
    try:
        search_input = page.locator('input[aria-label="Search query"]')
        search_input.click()
        random_short_wait()
        search_input.fill(query)
        random_short_wait()
        search_input.press("Enter")
        random_short_wait()
        # click 'Latest' to get newest tweets (adjust if localized)
        try:
            page.locator('text="Latest"').click()
        except Exception:
            # fallback: continue without clicking if selector fails
            print("Couldn't click 'Latest' — continuing with default search order.")
    except Exception as e:
        print("Search failed:", e)
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

    while True:
        new_tweet_appended, content_list, tweet_time, tweet_data = read_tweet_content(
            page, content_list, time_zone
        )

        if tweet_time is None:
            print("No tweet timestamp found; scrolling and retrying...")
            scroll_to_next_tweet(page)
            failed_reads += 1
            if failed_reads >= 8:
                print("Too many failed reads — aborting this query.")
                break
            continue
        else:
            failed_reads = 0  # ONLY reset failed-reads here

        # stop when older than start_date
        if tweet_time < start_date:
            if i == 1 and not content_list:
                print("NO TWEETS IN THE TIME FRAME")
            else:
                print("Reached tweets older than start_date; stopping scrape.")
            break

        # skip tweets newer than end_date
        if tweet_time > end_date:
            print("Found tweet newer than end_date — skipping and scrolling.")
            scroll_to_next_tweet(page)
            continue

        if new_tweet_appended and tweet_data is not None:
            consecutive_duplicates = 0  # reset ONLY when we got a new tweet

            print("------------------------------------------")
            print("TWEET #", i)
            print("APPENDED TWEET FROM TIME", tweet_time)
            print("CURRENT TWEET CONTENT:", content_list[-1][0][:140])  # preview

            try:
                write_single_tweet_to_csv(tweet_data, query, file_name)
            except Exception as e:
                print("Error writing tweet to CSV:", e)

            i += 1
            scroll_to_next_tweet(page)
        else:
            # duplicate / stall
            consecutive_duplicates += 1
            print("SCROLLING, TWEET WAS DUPLICATE OR ALREADY COLLECTED")

            if consecutive_duplicates >= 30:
                print(
                    "No new tweets after 30 duplicate/stall scrolls — stopping this query."
                )
                break

            scroll_to_next_tweet(page)

    return content_list


def read_tweet_content(page, content_list, time_zone):
    """
    Read the first tweet on the page.
    Returns (new_tweet_appended: bool, content_list: list, tweet_time: datetime|None, tweet_data|None)
    """
    new_tweet_appended = False
    tweet_data = None

    try:
        tweet_element = page.locator('article[data-testid="tweet"]').first
        tweet_element.wait_for(state="visible", timeout=10000)
    except TimeoutError:
        return new_tweet_appended, content_list, None, None
    except Exception:
        return new_tweet_appended, content_list, None, None

    try:
        html_content = tweet_element.inner_html()
    except Exception:
        return new_tweet_appended, content_list, None, None

    tweet_text = extract_tweet_text(html_content)
    tweet_analytics = extract_analytics(html_content)
    tweet_time = extract_time(html_content, time_zone)

    if tweet_text is None or tweet_analytics is None or tweet_time is None:
        return new_tweet_appended, content_list, None, None

    # ensure tz-aware
    if tweet_time.tzinfo is None:
        tweet_time = tweet_time.replace(tzinfo=time_zone)

    tweet_data = (tweet_text, tweet_analytics, tweet_time)

    # avoid duplicates (simple last-item check)
    if not content_list or content_list[-1] != tweet_data:
        content_list.append(tweet_data)
        new_tweet_appended = True

    return new_tweet_appended, content_list, tweet_time, tweet_data


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
