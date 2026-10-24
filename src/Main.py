"""Main controller for the Smart Class Planning Tool."""

import argparse
import json
import tempfile
from pathlib import Path

from CoursePlannerIntegration import TRACKS, build_integrated_plan
from CoursePlanExporter import export_course_plan
from DegreeWorksParser import extract_text_from_pdf, parse_courses
from InputValidator import validate_pdf


ROOT = Path(__file__).resolve().parent.parent


def run_application(args):
    """Parse student data, generate recommendations, and export to Excel."""
    if args.degreeworks_pdf:
        validate_pdf(str(args.degreeworks_pdf))
        text = extract_text_from_pdf(str(args.degreeworks_pdf))
        student_data = parse_courses(text)
    else:
        with open(args.degreeworks_json, "r", encoding="utf-8") as file:
            student_data = json.load(file)

    with tempfile.TemporaryDirectory(prefix="smart_class_") as directory:
        audit_path = Path(directory) / "student_audit.json"
        audit_path.write_text(
            json.dumps(student_data, indent=2),
            encoding="utf-8",
        )

        result = build_integrated_plan(
            track=args.track,
            start_semester=args.start,
            max_credits=args.max_credits,
            include_summer=not args.no_summer,
            study_plans_path=args.study_plans,
            degreeworks_path=audit_path,
            catalog_path=args.catalog,
            schedule_path=args.schedule,
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    export_course_plan(result, str(output))

    scheduled = sum(len(term["courses"]) for term in result["plan"])

    print("\nSMART CLASS PLANNING TOOL")
    print("=" * 50)
    print("Track:", result["track"])
    print("Starting semester:", result["start_semester"])
    print("Scheduled courses:", scheduled)
    print("Unscheduled courses:", len(result["unscheduled"]))
    print("Excel output:", output)

    for item in result["unscheduled"]:
        print("UNSCHEDULED:", item["course_code"], "-", item["reason"])

    for warning in result["warnings"]:
        print("WARNING:", warning)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate an academic course plan directly to Excel."
    )

    student_input = parser.add_mutually_exclusive_group(required=True)
    student_input.add_argument(
        "--degreeworks-pdf",
        type=Path,
        help="Student DegreeWorks PDF file.",
    )
    student_input.add_argument(
        "--degreeworks-json",
        type=Path,
        help="Previously parsed DegreeWorks JSON file.",
    )

    parser.add_argument("--track", choices=TRACKS, default="general")
    parser.add_argument("--start", default="Spring 2027")
    parser.add_argument("--max-credits", type=int, default=12)
    parser.add_argument("--no-summer", action="store_true")
    parser.add_argument(
        "--study-plans",
        type=Path,
        default=ROOT / "data" / "Graduate_Study_Plans.xlsx",
    )
    parser.add_argument(
        "--schedule",
        type=Path,
        default=ROOT / "data" / "4_year_schedule.xlsx",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "data" / "cpsc_course_catalog.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "recommended_plan.xlsx",
    )

    args = parser.parse_args()

    try:
        run_application(args)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
