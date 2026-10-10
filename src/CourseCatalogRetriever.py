import json
import os
import time

import requests
from bs4 import BeautifulSoup


CATALOG_URL = "https://catalog.columbusstate.edu/course-descriptions/cpsc/"

MAX_RETRIES = 3
REQUEST_TIMEOUT = 60
RETRY_DELAY = 5

OUTPUT_FILE = os.path.join(
    "data",
    "cpsc_course_catalog.json"
)


def fetch_catalog_page():
    """Download the official CSU CPSC course catalog page."""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/154.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"Connecting to CSU CPSC course catalog "
                f"(attempt {attempt}/{MAX_RETRIES})..."
            )

            response = requests.get(
                CATALOG_URL,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()
            return response.text

        except requests.exceptions.Timeout:
            print("The CSU catalog timed out.")

        except requests.exceptions.ConnectionError:
            print("Could not connect to the CSU catalog.")

        except requests.exceptions.HTTPError as error:
            print(
                f"CSU catalog returned an HTTP error: {error}"
            )
            raise

        if attempt < MAX_RETRIES:
            print(
                f"Waiting {RETRY_DELAY} seconds "
                "before retrying...\n"
            )
            time.sleep(RETRY_DELAY)

    raise ConnectionError(
        "Unable to retrieve the CSU catalog "
        "after multiple attempts."
    )


def parse_course_block(course_block):
    """
    Extract structured course information
    from one CSU catalog course block.
    """

    code_tag = course_block.select_one(".detail-code")
    title_tag = course_block.select_one(".detail-title")
    hours_tag = course_block.select_one(".detail-coursehours")

    if not code_tag or not title_tag:
        return None

    course_code = code_tag.get_text(
        " ",
        strip=True
    )

    title = title_tag.get_text(
        " ",
        strip=True
    )

    course_hours = (
        hours_tag.get_text(" ", strip=True)
        if hours_tag
        else None
    )

    description = None
    prerequisites = None
    restrictions = None

    for extra in course_block.select(".courseblockextra"):
        text = extra.get_text(
            " ",
            strip=True
        )

        if text.startswith("Prerequisite(s):"):
            prerequisites = text.replace(
                "Prerequisite(s):",
                "",
                1
            ).strip()

        elif text.startswith("Restriction(s):"):
            restrictions = text.replace(
                "Restriction(s):",
                "",
                1
            ).strip()

        elif description is None:
            description = text

    return {
        "course_code": course_code,
        "title": title,
        "course_hours": course_hours,
        "description": description,
        "prerequisites": prerequisites,
        "restrictions": restrictions
    }


def parse_catalog(html):
    """Parse all CPSC courses from the CSU catalog."""

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    courses = []

    course_blocks = soup.select(".courseblock")

    for block in course_blocks:
        course = parse_course_block(block)

        if course:
            courses.append(course)

    return courses


def save_catalog(courses):
    """
    Save parsed CPSC course information
    to a JSON file for use by other modules.
    """

    os.makedirs(
        os.path.dirname(OUTPUT_FILE),
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            courses,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(
        f"\nSaved {len(courses)} courses to "
        f"{OUTPUT_FILE}"
    )


def print_course(course):
    """Print one course in a readable format."""

    print("\n----------------------------------------")
    print(f"Course: {course['course_code']}")
    print(f"Title: {course['title']}")
    print(f"Hours: {course['course_hours']}")

    print(
        "Prerequisites:",
        course["prerequisites"]
        if course["prerequisites"]
        else "None listed"
    )

    print(
        "Restrictions:",
        course["restrictions"]
        if course["restrictions"]
        else "None listed"
    )


def main():
    """
    Retrieve, parse, test, and store
    CSU CPSC course catalog information.
    """

    try:
        html = fetch_catalog_page()

        courses = parse_catalog(html)

        if not courses:
            print(
                "\nError: No CPSC courses were found "
                "in the catalog."
            )
            return

        print(
            f"\nSuccessfully parsed {len(courses)} "
            "CPSC courses."
        )

        save_catalog(courses)

        # Display several courses as a basic verification test.
        test_courses = {
            "CPSC 1302K",
            "CPSC 6125",
            "CPSC 6177"
        }

        for course in courses:
            if course["course_code"] in test_courses:
                print_course(course)

    except requests.RequestException as error:
        print(
            f"\nError retrieving CSU course catalog: {error}"
        )

    except ConnectionError as error:
        print(f"\nError: {error}")

    except OSError as error:
        print(
            f"\nError saving course catalog data: {error}"
        )


if __name__ == "__main__":
    main()