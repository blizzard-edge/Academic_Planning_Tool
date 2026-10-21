
"""SCPTAA_001 - Integration for the Smart Class Planning Tool.

Reads graduate study plans and connects them to the existing
CoursePlanner scheduling engine.

This module does not modify teammates' parser modules.
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
    )
except ImportError:
    from CoursePlanner import (
        build_course_plan,
        load_course_offerings,
        normalize_course_code,
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
    """Load a JSON document."""
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def extract_course_codes(value):
    """Extract explicit course codes without inventing any."""
    if value is None:
        return []

    if not isinstance(value, str):
        return []

    text = value.replace("\u00c2", "").replace("\u00a0", " ")
    matches = COURSE_PATTERN.findall(text.upper())

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
    """Extract an ordered course list from the ACS study-plan sheet.

    Track:
        software, ai, general

    Start season:
        fall, spring

    Elective and other non-course placeholders are recorded as
    warnings rather than scheduled as actual courses.
    """
    track = track.lower().strip()
    start_season = start_season.lower().strip()

    if track not in TRACK_ROWS:
        raise ValueError(
            "Unknown track. Choose software, ai, or general."
        )

    if start_season not in TRACK_ROWS[track]:
        raise ValueError(
            "Start season must be fall or spring."
        )

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


def build_integrated_plan(
    track="general",
    start_semester="Fall 2026",
    max_credits=12,
    include_summer=True,
    study_plans_path=DEFAULT_STUDY_PLANS,
    degreeworks_path=DEFAULT_DEGREEWORKS,
    catalog_path=DEFAULT_CATALOG,
    schedule_path=DEFAULT_SCHEDULE,
):
    """Build a course plan using all four project data sources."""
    start_season = start_semester.split()[0].lower()

    if start_season not in {"fall", "spring"}:
        raise ValueError(
            "Study-plan entry must begin in Fall or Spring."
        )

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

    result = build_course_plan(
        required_courses=study_plan["required_courses"],
        degreeworks_data=degreeworks,
        course_catalog=catalog,
        offering_schedule=offerings,
        start_semester=start_semester,
        max_credits=max_credits,
        include_summer=include_summer,
    )

    result["track"] = study_plan["track"]
    result["start_semester"] = start_semester
    result["required_courses"] = study_plan["required_courses"]

    result["warnings"] = (
        study_plan["warnings"] + result["warnings"]
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
        default="Fall 2026",
        help="Starting semester, e.g. 'Fall 2026'.",
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

    for semester in result["plan"]:
        if not semester["courses"]:
            continue

        total_credits = sum(
            course["credits"]
            for course in semester["courses"]
        )

        print(
            f"{semester['semester']} "
            f"({total_credits} credits)"
        )

        for course in semester["courses"]:
            print(
                f"  {course['course_code']} - "
                f"{course['title']}"
            )

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
            json.dump(
                result,
                file,
                indent=2,
            )

        print()
        print("JSON saved to:", args.output)


if __name__ == "__main__":
    main()
