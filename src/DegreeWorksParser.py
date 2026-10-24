
from pypdf import PdfReader
import re
import sys
import os
import json


OUTPUT_FILE = os.path.join(
    "data",
    "degree_works_info.json"
)

def extract_text_from_pdf(pdf_path):
    """Extract text from every page of a DegreeWorks PDF."""
    reader = PdfReader(pdf_path)

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)


COURSE_CODE = r"[A-Z]{4}\s+\d{4}[A-Z]?"

# A course code starts where no capital letter or digit comes right before it,
# and its "subject" is never the season word FALL (e.g. "FALL 2025").
CODE_START = r"(?<![A-Z0-9])(?!FALL\s)"

# Words that show a requirement title was cut off at the end of a line.
CONTINUATION_WORDS = {"and", "of", "for", "in", "the", "to", "with", "&", "a", "an"}


def _remove_notes_section(text):
    """Drop the advisor 'Notes' section (up to 'Legend' or 'Disclaimer')."""
    kept = []
    in_notes = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "Notes":
            in_notes = True
            continue
        if in_notes and stripped.startswith(("Legend", "Disclaimer")):
            in_notes = False
        if not in_notes:
            kept.append(line)

    return "\n".join(kept)


def _clean_title(text):
    """Cut a requirement title before any course code or 'Still needed'."""
    text = re.split(rf"{CODE_START}{COURSE_CODE}|Still needed", text)[0]
    return text.strip(" -")


def _requirement_title(text, following_lines):
    """Return a requirement title, joining a label that wrapped onto a later line.

    A title ending in a word like "and" was cut off. The rest is on one of
    the next few lines; lines that begin with another course code belong to
    other rows and are skipped.
    """
    title = _clean_title(text)
    words = title.split()

    if words and words[-1].lower() in CONTINUATION_WORDS:
        for line in following_lines[:3]:
            if re.match(rf"\s*{COURSE_CODE}", line):
                continue
            continuation = _clean_title(line)
            if continuation:
                title = f"{title} {continuation}"
            break

    return title


def parse_courses(text):
    """
    Parse course records from a DegreeWorks audit.

    Courses are classified as:
    - COMPLETED: course has a final letter grade
    - IN_PROGRESS: course is marked CURR
    - REMAINING: required course appears in the requirement section
      but has not been completed or started
    """

    completed = {}
    in_progress = {}
    remaining = {}

    # Advisor notes are free text ("Fall 2025 - CPSC 6119, ...") and are
    # not degree requirements, so they are excluded before parsing.
    text = _remove_notes_section(text)

    # Find actual course records with grades/statuses.
    # - Case-sensitive, so words such as "Fall" are never read as a subject.
    # - The title may not contain another course code, so when a wrapped
    #   requirement label shares a line with a course record, the match
    #   starts at the course record's own code.
    # - (?<![A-Z0-9]) instead of \b, so "DesignCPSC 6109" still matches.
    # - A record must sit on one line ([ \t] instead of \s), so a
    #   "Still needed ... CPSC 6179" line cannot merge with the next line's
    #   record and steal its grade.
    course_pattern = re.compile(
        rf"{CODE_START}([A-Z]{{4}})[ \t]+(\d{{4}}[A-Z]?)[ \t]+"
        rf"((?:(?!{COURSE_CODE}).)+?)[ \t]+"
        r"(CURR|[ABCDF][+-]?)[ \t]+\(?(\d+)\)?[ \t]+"
        r"(Spring|Summer|Fall)[ \t]+(\d{4})"
    )

    for match in course_pattern.finditer(text):
        subject = match.group(1).upper()
        number = match.group(2).upper()
        title = match.group(3).strip()
        grade = match.group(4).upper()
        credits = int(match.group(5))
        term = match.group(6)
        year = int(match.group(7))

        course_code = f"{subject} {number}"

        course = {
            "course_code": course_code,
            "title": title,
            "credits": credits,
            "term": f"{term} {year}"
        }

        if grade == "CURR":
            course["status"] = "IN_PROGRESS"
            in_progress[course_code] = course
        else:
            course["status"] = "COMPLETED"
            course["grade"] = grade
            completed[course_code] = course

    # DegreeWorks can list required courses before the actual course record.
    # Find those requirement-style entries ("CPSC 6179- Software ...").
    requirement_pattern = re.compile(
        rf"{CODE_START}([A-Z]{{4}})\s+(\d{{4}}[A-Z]?)\s*-\s*([^\n]*)"
    )

    lines = text.splitlines()

    for index, line in enumerate(lines):
        for match in requirement_pattern.finditer(line):
            subject = match.group(1)
            number = match.group(2)
            course_code = f"{subject} {number}"

            # If the course already has a completed or current record,
            # it is not a remaining course.
            if course_code in completed or course_code in in_progress:
                continue

            title = _requirement_title(match.group(3), lines[index + 1:])

            remaining[course_code] = {
                "course_code": course_code,
                "title": title,
                "status": "REMAINING"
            }

    return {
        "completed_courses": list(completed.values()),
        "in_progress_courses": list(in_progress.values()),
        "remaining_courses": list(remaining.values())
    }

def save_degree_progress(degree_progress):
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
            degree_progress,
            file,
            indent=4,
            ensure_ascii=False
        )


def print_course_results(result):
    """Display parsed DegreeWorks course information."""

    print("\nCOMPLETED COURSES")
    print("-----------------")

    if result["completed_courses"]:
        for course in result["completed_courses"]:
            print(
                course["course_code"],
                "|",
                course["grade"],
                "|",
                course["term"]
            )
    else:
        print("None")

    print("\nIN-PROGRESS COURSES")
    print("-------------------")

    if result["in_progress_courses"]:
        for course in result["in_progress_courses"]:
            print(
                course["course_code"],
                "|",
                course["term"]
            )
    else:
        print("None")

    print("\nREMAINING COURSES")
    print("-----------------")

    if result["remaining_courses"]:
        for course in result["remaining_courses"]:
            print(
                course["course_code"],
                "|",
                course["title"]
            )
    else:
        print("None")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/DegreeWorksParser.py <degreeworks_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    if not pdf_path.lower().endswith(".pdf"):
        print("Error: DegreeWorks input must be a PDF file.")
        sys.exit(1)

    try:
        degreeworks_text = extract_text_from_pdf(pdf_path)
        result = parse_courses(degreeworks_text)
        save_degree_progress(result)
        print_course_results(result)

    except Exception as error:
        print(f"Error reading DegreeWorks PDF: {error}")
        sys.exit(1)
