from pypdf import PdfReader
import re


def extract_text_from_pdf(pdf_path):
    """Extract text from every page of a DegreeWorks PDF."""
    reader = PdfReader(pdf_path)

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)


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

    # Find actual course records with grades/statuses.
    course_pattern = re.compile(
        r"\b([A-Z]{4})\s+(\d{4})\s+(.+?)\s+"
        r"(CURR|A|B|C|D|F)\s+\(?(\d+)\)?\s+"
        r"(Spring|Summer|Fall)\s+(\d{4})",
        re.IGNORECASE
    )

    for match in course_pattern.finditer(text):
        subject = match.group(1).upper()
        number = match.group(2)
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
    # Find those requirement-style entries.
    requirement_pattern = re.compile(
        r"\b([A-Z]{4})\s+(\d{4})\s*-\s*([^\n]+)",
        re.IGNORECASE
    )

    for match in requirement_pattern.finditer(text):
        subject = match.group(1).upper()
        number = match.group(2)
        title = match.group(3).strip()

        course_code = f"{subject} {number}"

        # If the course already has a completed or current record,
        # it is not a remaining course.
        if course_code in completed or course_code in in_progress:
            continue

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
    pdf_path = "local_test_data/degree work.pdf"

    degreeworks_text = extract_text_from_pdf(pdf_path)
    result = parse_courses(degreeworks_text)

    print_course_results(result)