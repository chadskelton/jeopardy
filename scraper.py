# This is a template for a Python scraper on morph.io (https://morph.io)
# including some code snippets below that you should find helpful

# import scraperwiki
# import lxml.html
#
# # Read in a page
# html = scraperwiki.scrape("http://foo.com")
#
# # Find something on the page using css selectors
# root = lxml.html.fromstring(html)
# root.cssselect("div[align='left']")
#
# # Write out to the sqlite database using scraperwiki library
# scraperwiki.sqlite.save(unique_keys=['name'], data={"name": "susan", "occupation": "software developer"})
#
# # An arbitrary query against the database
# scraperwiki.sql.select("* from data where 'name'='peter'")

# You don't have to do things with the ScraperWiki and lxml libraries.
# You can use whatever libraries you want: https://morph.io/documentation/python
# All that matters is that your final data is written to an SQLite database
# called "data.sqlite" in the current working directory which has at least a table
# called "data".

import os
import requests
from bs4 import BeautifulSoup
import scraperwiki


# You can override this in morph.io settings as an environment variable
# e.g. MORPH_START_URLS="https://j-archive.com/showgame.php?game_id=6680 https://j-archive.com/showgame.php?game_id=6681"
DEFAULT_START_URLS = [
    "https://j-archive.com/showgame.php?game_id=6680",
]


def get_start_urls():
    env_urls = os.environ.get("MORPH_START_URLS")
    if env_urls:
        # split on whitespace so you can pass space- or newline-delimited URLs
        return [u.strip() for u in env_urls.split() if u.strip()]
    return DEFAULT_START_URLS


def extract_clues_from_soup(soup, game_url):
    """Return a list of dicts with question, answer, and some metadata."""
    records = []

    # Game title (e.g., "Show #8227 - Tuesday, June 2, 2020")
    game_title_el = soup.select_one("#game_title h1")
    game_title = game_title_el.get_text(strip=True) if game_title_el else None

    # For each clue cell on the page
    for clue_td in soup.select("td.clue"):
        # Each clue cell contains two <td class="clue_text">:
        #   1) question
        #   2) hidden answer block (with <em class="correct_response"> inside)
        clue_text_tds = clue_td.find_all("td", class_="clue_text")
        if len(clue_text_tds) < 2:
            continue

        # Question
        question_td = clue_text_tds[0]
        question = question_td.get_text(" ", strip=True)

        # Answer (correct response)
        answer_td = clue_text_tds[1]
        correct = answer_td.find("em", class_="correct_response")
        answer = correct.get_text(" ", strip=True) if correct else None

        if not question or not answer:
            continue

        # Dollar value + Daily Double?
        value = None
        is_daily_double = False
        header = clue_td.select_one("table.clue_header")
        if header:
            value_cell = header.select_one(".clue_value, .clue_value_daily_double")
            if value_cell:
                value = value_cell.get_text(" ", strip=True)
                if "DD:" in value:
                    is_daily_double = True

        # Round ("Jeopardy", "Double Jeopardy", "Final Jeopardy")
        round_name = None
        round_div = clue_td.find_parent(
            "div", id=lambda x: x and x.endswith("_round")
        )
        if round_div:
            rid = round_div.get("id")
            if rid == "jeopardy_round":
                round_name = "Jeopardy!"
            elif rid == "double_jeopardy_round":
                round_name = "Double Jeopardy!"
            elif rid == "final_jeopardy_round":
                round_name = "Final Jeopardy!"

        # Category for that clue
        category = None
        table_round = (
            clue_td.find_parent("table", class_="round")
            or (round_div.find("table", class_="final_round") if round_div else None)
        )

        if table_round:
            # All category names for that round
            categories = [
                td.get_text(" ", strip=True)
                for td in table_round.select("td.category .category_name")
            ]

            # Determine which column (0–5) this clue is in
            tr = clue_td.parent  # row that the clue cell sits in
            row_clue_tds = [
                td for td in tr.find_all("td", recursive=False)
                if "clue" in (td.get("class") or [])
            ]
            try:
                col_index = row_clue_tds.index(clue_td)
                if 0 <= col_index < len(categories):
                    category = categories[col_index]
            except ValueError:
                pass

        record = {
            "game_url": game_url,
            "game_title": game_title,
            "round": round_name,
            "category": category,
            "value": value,
            "is_daily_double": is_daily_double,
            "question": question,
            "answer": answer,
        }

        records.append(record)

    return records


def scrape_game(game_url):
    print("Scraping {}...".format(game_url))
    resp = requests.get(game_url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    records = extract_clues_from_soup(soup, game_url)

    # Save records to morph.io's SQLite DB
    for rec in records:
        scraperwiki.sqlite.save(
            unique_keys=["game_url", "question"],
            data=rec,
        )
    print("Saved {} clues from {}.".format(len(records), game_url))


if __name__ == "__main__":
    for url in get_start_urls():
        scrape_game(url)
