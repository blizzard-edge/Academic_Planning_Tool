
"""SCPTAA_001 - Integration for the Smart Class Planning Tool.

Connects graduate study plans, DegreeWorks progress, the course
catalog, and the four-year course schedule.

Missing catalog entries may be supplemented by explicitly verified
study-plan information. Unknown prerequisites are never assumed met.
"""

import argparse
import json
import re
from pathlib import Path

from openpyxl import load_workbook

try:
    from .CoursePlanner import (
        build_course_plan,
        load_course_offerings,
        normalize_course_code,
        semester_sort_key,
    )
except ImportError:
    from CoursePlanner import (
        build_course_plan,
        load_course_offerings,
        normalize_course_code,
        semester_sort_key,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_STUDY_PLANS = PROJECT_ROOT / "data" / "Graduate_Study_Plans.xlsx"
DEFAULT_DEGREEWORKS = PROJECT_ROOT / "data" / "degree_works_info.json"
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "cpsc_course_catalog.json"
DEFAULT_SCHEDULE = PROJECT_ROOT / "data" / "4_year_schedule.xlsx"

COURSE_PATTERN = re.compile(r"\b[A-Z]{4}\s*\d{4}[A-Z]?\b")

TRACK_ROWS = {
    "software": {
        "fall": (22, 24),
        "spring": (25, 27),
    },
    "ai": {
        "fall": (29, 31),
        "spring": (32, 34),
    },
    "general": {
        "fall": (36, 38),
        "spring": (39, 41),
    },
}

TRACK_LABELS = {
    "software": "ACS - Software Development",
    "ai": "ACS - AI and Data Science",
    "general": "ACS - General",
}

START_COLUMNS = {
    "fall": (4, 8),
    "spring": (4, 8),
}


def load_json(path):
    """Read a JSON file."""
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def extract_course_codes(value):
    """Extract explicit course codes without inventing any."""
    if not isinstance(value, str):
        return []

    text = value.replace("\u00c2", "").replace("\u00a0", " ").upper()
    matches = COURSE_PATTERN.findall(text)

    codes = []
    for match in matches:
        match = re.sub(
            r"^([A-Z]{4})(\d{4})",
            r"\1 \2",
            match,
        )
        code = normalize_course_code(match)
        if code not in codes:
            codes.append(code)

    return codes


def read_study_plan(
    workbook_path,
    track="general",
    start_season="fall",
):
    """Read ordered ACS core courses from the graduate study plan.

    This reader is provisional. Joshua's dedicated parser can replace
    it without changing the scheduling engine.
    """
    track = track.lower().strip()
    start_season = start_season.lower().strip()

    if track not in TRACK_ROWS:
        raise ValueError(
            "Unknown track. Choose software, ai, or general."
        )

    if start_season not in TRACK_ROWS[track]:
        raise ValueError("Start season must be fall or spring.")

    workbook = load_workbook(
        workbook_path,
        read_only=True,
        data_only=True,
    )

    try:
        if "Sheet1" not in workbook.sheetnames:
            raise ValueError(
                "Graduate study-plan worksheet 'Sheet1' not found."
            )

        sheet = workbook["Sheet1"]
        first_row, last_row = TRACK_ROWS[track][start_season]
        first_column, last_column = START_COLUMNS[start_season]

        required_courses = []
        seen = set()
        warnings = []

        for column in range(first_column, last_column + 1):
            for row in range(first_row, last_row + 1):
                value = sheet.cell(row, column).value
                if value is None:
                    continue

                codes = extract_course_codes(value)

                if codes:
                    for code in codes:
                        if code not in seen:
                            seen.add(code)
                            required_courses.append(code)
                else:
                    text = str(value).strip()
                    if text and (
                        "elective" in text.lower()
                        or "msol" in text.lower()
                    ):
                        warnings.append(
                            f"Placeholder excluded: {text}"
                        )

        return {
            "track": TRACK_LABELS[track],
            "start_season": start_season.title(),
            "required_courses": required_courses,
            "warnings": warnings,
        }

    finally:
        workbook.close()


def find_study_plan_course_details(workbook_path, course_codes):
    """Inspect study-plan workbook rows for explicit course metadata.

    Looks for a matching course code and nearby credit/prerequisite
    fields. Missing values remain unknown rather than being invented.
    """
    requested = set(course_codes)
    details = {}

    workbook = load_workbook(
        workbook_path,
        read_only=True,
        data_only=True,
    )

    try:
        if "Courses" not in workbook.sheetnames:
            return details

        sheet = workbook["Courses"]

        for row in sheet.iter_rows(values_only=True):
            if not row:
                continue

            matching = []

            for value in row:
                if isinstance(value, str):
                    matching.extend(extract_course_codes(value))

            matching = set(matching) & requested

            if not matching:
                continue

            for code in matching:
                if code in details:
                    continue

                details[code] = {
                    "course_code": code,
                    "row_values": list(row),
                }

        return details

    finally:
        workbook.close()


def find_schedule_course_titles(workbook_path, course_codes):
    """Find official course titles from the schedule workbook."""
    requested = set(course_codes)
    titles = {}

    workbook = load_workbook(
        workbook_path,
        read_only=True,
        data_only=True,
    )

    try:
        sheet = workbook.active

        for row in sheet.iter_rows(
            min_row=4,
            min_col=1,
            max_col=2,
            values_only=True,
        ):
            code = normalize_course_code(row[0])

            if code in requested and isinstance(row[1], str):
                titles[code] = row[1].strip()

        return titles

    finally:
        workbook.close()


def supplement_missing_catalog_courses(
    required_courses,
    catalog,
    offerings,
    study_plans_path,
    schedule_path,
):
    """Add provisional records only when official offerings exist.

    For missing catalog courses, use the schedule title and an
    explicitly provisional 3-credit estimate. Do not fabricate
    prerequisites; mark those requirements as unverified.
    """
    known = {
        normalize_course_code(course.get("course_code"))
        for course in catalog
        if isinstance(course, dict)
    }

    missing = [
        code for code in required_courses
        if code not in known and code in offerings
    ]

    if not missing:
        return catalog, {}, []

    titles = find_schedule_course_titles(
        schedule_path,
        missing,
    )

    study_details = find_study_plan_course_details(
        study_plans_path,
        missing,
    )

    augmented = list(catalog)
    provisional = {}
    warnings = []

    for code in missing:
        title = titles.get(code, code)

        # Three credits is a planning assumption, not a
        # verified catalog fact. Keep that distinction visible.
        estimated_credits = 3

        augmented.append({
            "course_code": code,
            "title": title,
            "credits": estimated_credits,
            "prerequisites": None,
        })

        provisional[code] = {
            "estimated_credits": estimated_credits,
            "prerequisites_verified": False,
            "study_plan_record_found": code in study_details,
        }

        warnings.append(
            f"{code}: provisional {estimated_credits}-credit "
            "planning estimate; prerequisites and credit hours "
            "require advisor verification."
        )

    return augmented, provisional, warnings


def build_integrated_plan(
    track="general",
    start_semester="Spring 2027",
    max_credits=12,
    include_summer=True,
    study_plans_path=DEFAULT_STUDY_PLANS,
    degreeworks_path=DEFAULT_DEGREEWORKS,
    catalog_path=DEFAULT_CATALOG,
    schedule_path=DEFAULT_SCHEDULE,
):
    """Build a plan using all four university data sources."""
    start_season = start_semester.split()[0].lower()

    if start_season not in {"fall", "spring"}:
        raise ValueError(
            "Study-plan entry must begin in Fall or Spring."
        )

    semester_sort_key(start_semester)

    study_plan = read_study_plan(
        study_plans_path,
        track=track,
        start_season=start_season,
    )

    degreeworks = load_json(degreeworks_path)
    catalog = load_json(catalog_path)

    offerings = load_course_offerings(
        schedule_path,
        start_semester=start_semester,
    )

    catalog, provisional, catalog_warnings = (
        supplement_missing_catalog_courses(
            study_plan["required_courses"],
            catalog,
            offerings,
            study_plans_path,
            schedule_path,
        )
    )

    result = build_course_plan(
        required_courses=study_plan["required_courses"],
        degreeworks_data=degreeworks,
        course_catalog=catalog,
        offering_schedule=offerings,
        start_semester=start_semester,
        max_credits=max_credits,
        include_summer=include_summer,
        current_semester="Fall 2026",
    )

    for semester in result["plan"]:
        for course in semester["courses"]:
            code = course["course_code"]
            if code in provisional:
                note = (
                    "PROVISIONAL: estimated 3 credits; "
                    "prerequisites and credit hours unverified"
                )
                existing = course.get("notes", "")
                course["notes"] = (
                    existing + "; " + note
                    if existing else note
                )

    result["track"] = study_plan["track"]
    result["start_semester"] = start_semester
    result["required_courses"] = study_plan["required_courses"]
    result["provisional_courses"] = provisional

    result["warnings"] = (
        study_plan["warnings"]
        + catalog_warnings
        + result["warnings"]
    )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate an ACS semester-by-semester course plan."
    )

    parser.add_argument(
        "--track",
        choices=["software", "ai", "general"],
        default="general",
    )

    parser.add_argument(
        "--start",
        default="Spring 2027",
        help="Starting semester, e.g. 'Spring 2027'.",
    )

    parser.add_argument(
        "--max-credits",
        type=int,
        default=12,
    )

    parser.add_argument(
        "--no-summer",
        action="store_true",
    )

    parser.add_argument(
        "--study-plans",
        type=Path,
        default=DEFAULT_STUDY_PLANS,
    )

    parser.add_argument(
        "--degreeworks",
        type=Path,
        default=DEFAULT_DEGREEWORKS,
    )

    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
    )

    parser.add_argument(
        "--schedule",
        type=Path,
        default=DEFAULT_SCHEDULE,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )

    args = parser.parse_args()

    result = build_integrated_plan(
        track=args.track,
        start_semester=args.start,
        max_credits=args.max_credits,
        include_summer=not args.no_summer,
        study_plans_path=args.study_plans,
        degreeworks_path=args.degreeworks,
        catalog_path=args.catalog,
        schedule_path=args.schedule,
    )

    print()
    print("SMART CLASS PLANNING TOOL")
    print("=" * 50)
    print("Track:", result["track"])
    print("Starting semester:", result["start_semester"])
    print("Required courses:", len(result["required_courses"]))

    print()
    print("RECOMMENDED COURSE PLAN")
    print("-" * 50)

    scheduled_count = 0

    for semester in result["plan"]:
        if not semester["courses"]:
            continue

        credits = sum(
            course["credits"]
            for course in semester["courses"]
        )

        print(
            f"{semester['semester']} ({credits} credits)"
        )

        for course in semester["courses"]:
            scheduled_count += 1
            print(
                f"  {course['course_code']} - "
                f"{course['title']}"
            )
            if course.get("notes"):
                print(f"    NOTE: {course['notes']}")

    if scheduled_count == 0:
        print("No additional courses scheduled.")

    print()
    print("UNSCHEDULED COURSES")
    print("-" * 50)

    if result["unscheduled"]:
        for course in result["unscheduled"]:
            print(
                f"{course['course_code']}: "
                f"{course['reason']}"
            )
    else:
        print("None")

    if result["warnings"]:
        print()
        print("WARNINGS")
        print("-" * 50)
        for warning in result["warnings"]:
            print("-", warning)

    if args.output:
        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            args.output,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(result, file, indent=2)

        print()
        print("JSON saved to:", args.output)


if __name__ == "__main__":
    main()
