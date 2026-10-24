
"""SCPTAA_001 - Integration for the Smart Class Planning Tool.

Connects graduate study plans, DegreeWorks progress, the course
catalog, and the four-year course schedule.

The study plan and four-year schedule are read with the team's
dedicated parsers (GraduateStudyPlanParser and FourYearScheduleParser,
SCPTAA_004 / SCPTAA_005). This module only adapts their output to the
format the scheduling engine in CoursePlanner expects.

Missing catalog entries may be supplemented by study-plan information.
Unknown prerequisites are never assumed met.
"""

import argparse
import json
import re
from pathlib import Path

try:
    from .CoursePlanner import build_course_plan, normalize_course_code, semester_sort_key
    from .FourYearScheduleParser import load_four_year_schedule
    from .GraduateStudyPlanParser import load_graduate_study_plan
except ImportError:
    from CoursePlanner import build_course_plan, normalize_course_code, semester_sort_key
    from FourYearScheduleParser import load_four_year_schedule
    from GraduateStudyPlanParser import load_graduate_study_plan


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_STUDY_PLANS = PROJECT_ROOT / "data" / "Graduate_Study_Plans.xlsx"
DEFAULT_DEGREEWORKS = PROJECT_ROOT / "data" / "degree_works_info.json"
DEFAULT_CATALOG = PROJECT_ROOT / "data" / "cpsc_course_catalog.json"
DEFAULT_SCHEDULE = PROJECT_ROOT / "data" / "4_year_schedule.xlsx"

COURSE_PATTERN = re.compile(r"\b[A-Z]{4}\s*\d{4}[A-Z]?\b")

# Command-line track names -> track labels as they appear in the study plan.
# Labels are compared after removing spaces and hyphens, so spacing
# differences in the spreadsheet ("CYBR -Cyber Defense") do not matter.
TRACKS = {
    "general": "ACS - General",
    "software": "ACS - Software Dev",
    "ai": "ACS - AI and Data Science",
    "cyber-defense": "CYBR - Cyber Defense",
    "cyber-management": "CYBR - Management",
}

PROVISIONAL_CREDITS = 3


def load_json(path):
    """Read a JSON file."""
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def extract_course_codes(value):
    """Extract explicit course codes without inventing any."""
    if not isinstance(value, str):
        return []

    text = value.replace("Â", "").replace(" ", " ").upper()
    codes = []
    for match in COURSE_PATTERN.findall(text):
        match = re.sub(r"^([A-Z]{4})(\d{4})", r"\1 \2", match)
        code = normalize_course_code(match)
        if code not in codes:
            codes.append(code)
    return codes


def _label_key(label):
    """Compare track labels without spaces, hyphens or case."""
    return re.sub(r"[\s\-]+", "", str(label or "")).lower()


def required_courses_from_study_plan(study_plan, track, start_season):
    """Return the ordered course list for one track and start season.

    Uses the semester blocks produced by GraduateStudyPlanParser.
    Elective and MSOL placeholders are reported as warnings, not scheduled.
    """
    track = track.lower().strip()
    if track not in TRACKS:
        raise ValueError(
            "Unknown track. Choose one of: " + ", ".join(TRACKS) + "."
        )

    wanted_track = _label_key(TRACKS[track])
    wanted_start = f"{start_season.lower().strip()} start"

    for plan in study_plan["plans"]:
        if (_label_key(plan["track"]) == wanted_track
                and str(plan["start"]).strip().lower() == wanted_start):
            required = []
            template_semester = {}
            warnings = []
            for semester in plan["semesters"]:
                for entry in semester["entries"]:
                    codes = extract_course_codes(entry)
                    if codes:
                        for code in codes:
                            if code not in required:
                                required.append(code)
                                template_semester[code] = semester["number"]
                    elif "elective" in entry.lower() or "msol" in entry.lower():
                        warnings.append(f"Placeholder excluded: {entry}")
            return {
                "track": plan["track"],
                "start_season": start_season.title(),
                "required_courses": required,
                "template_semester": template_semester,
                "warnings": warnings,
            }

    raise ValueError(
        f"The study plan has no '{TRACKS[track]}' track with a "
        f"{start_season.title()} start."
    )


def offerings_from_schedule(schedule, start_semester, courses_of_interest=()):
    """Convert FourYearScheduleParser output to {course: ["Fall 2026", ...]}.

    Only terms on or after start_semester are kept. Following the Demo 1
    design, a cell containing "?" is uncertain and is treated as NOT
    offered; a warning is returned for courses the plan cares about.
    """
    start_key = semester_sort_key(start_semester)
    interest = set(courses_of_interest)
    offerings = {}
    warnings = []

    for code, course in schedule["courses"].items():
        for term in schedule["terms"]:
            name = f"{term['season']} {term['year']}"
            if semester_sort_key(name) < start_key:
                continue

            cell = course["terms"][term["code"]]
            if not cell["offered"]:
                continue

            if "?" in (cell["raw"] or ""):
                if code in interest:
                    warnings.append(
                        f"{code}: uncertain offering '{cell['raw']}' in "
                        f"{name} treated as not offered."
                    )
                continue

            offerings.setdefault(code, []).append(name)

    return offerings, warnings


def resolve_study_plan_prerequisite(text, known_codes):
    """Turn study-plan shorthand such as '6126 & 6157' into catalog form.

    Bare course numbers are matched against the study plan's own course
    list (6126 -> CYBR 6126, 6157 -> CPSC 6157). A number that matches
    zero or several courses is returned unchanged, so the planner's
    prerequisite parser rejects it and the course goes to advisor review
    instead of being scheduled on a guess.
    """
    if not text:
        return None

    by_number = {}
    for code in known_codes:
        number = code.split()[-1]
        by_number.setdefault(number, []).append(code)

    def replace(match):
        if match.group(1):
            return normalize_course_code(match.group(0))
        number = match.group(2)
        candidates = by_number.get(number, [])
        if len(candidates) == 1:
            return candidates[0]
        return match.group(0)

    resolved = re.sub(
        r"\b([A-Z]{4}\s*)?(\d{4}[A-Z]?)\b",
        replace,
        text.upper(),
    )
    resolved = resolved.replace("&", " AND ")
    return re.sub(r"\s+", " ", resolved).strip()


def supplement_missing_catalog_courses(required_courses, catalog, offerings, study_plan, schedule):
    """Add provisional records for required courses missing from the catalog.

    Uses the schedule title, an explicitly provisional credit estimate,
    and the study plan's prerequisite column. Courses without an official
    offering are left out so they are reported as unscheduled.
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

    study_courses = study_plan.get("courses", {})
    augmented = list(catalog)
    provisional = {}
    warnings = []

    for code in missing:
        schedule_record = schedule["courses"].get(code, {})
        study_record = study_courses.get(code, {})
        title = (
            schedule_record.get("title")
            or study_record.get("course_name")
            or code
        )
        prerequisites = resolve_study_plan_prerequisite(
            study_record.get("prerequisite"),
            study_courses.keys(),
        )

        augmented.append({
            "course_code": code,
            "title": title,
            "credits": PROVISIONAL_CREDITS,
            "prerequisites": prerequisites,
        })

        provisional[code] = {
            "estimated_credits": PROVISIONAL_CREDITS,
            "prerequisites": prerequisites,
            "prerequisite_source": "study plan" if study_record else "none found",
        }

        source = (
            f"prerequisites taken from the study plan ({prerequisites})"
            if prerequisites else
            "no prerequisites listed in the study plan"
        )
        warnings.append(
            f"{code}: not in the CPSC catalog; provisional "
            f"{PROVISIONAL_CREDITS}-credit estimate, {source}. "
            "Requires advisor verification."
        )

    return augmented, provisional, warnings


def template_prerequisite_conflicts(study_plan, catalog):
    """Warn where the official study-plan template places a course in the
    same semester as (or before) one of its own prerequisites.

    The planner always schedules prerequisites in an earlier term, so its
    plan will differ from the template there. This does not change the
    prerequisite policy; it makes the difference visible for an advisor.
    """
    records = {
        normalize_course_code(course.get("course_code")): course
        for course in catalog
        if isinstance(course, dict)
    }
    semester_of = study_plan["template_semester"]
    warnings = []

    for code, semester in semester_of.items():
        prerequisite_text = (records.get(code) or {}).get("prerequisites")
        for needed in extract_course_codes(prerequisite_text):
            if needed in semester_of and semester_of[needed] >= semester:
                warnings.append(
                    f"{code}: the study-plan template lists it in semester "
                    f"{semester}, with its prerequisite {needed} in semester "
                    f"{semester_of[needed]}. The plan schedules {code} after "
                    f"{needed}; confirm with an advisor whether concurrent "
                    "enrollment is allowed."
                )

    return warnings


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
        raise ValueError("Study-plan entry must begin in Fall or Spring.")

    semester_sort_key(start_semester)

    study_plan_data = load_graduate_study_plan(str(study_plans_path))
    study_plan = required_courses_from_study_plan(
        study_plan_data,
        track=track,
        start_season=start_season,
    )

    degreeworks = load_json(degreeworks_path)
    catalog = load_json(catalog_path)

    schedule = load_four_year_schedule(str(schedule_path))
    offerings, offering_warnings = offerings_from_schedule(
        schedule,
        start_semester,
        courses_of_interest=study_plan["required_courses"],
    )

    catalog, provisional, catalog_warnings = supplement_missing_catalog_courses(
        study_plan["required_courses"],
        catalog,
        offerings,
        study_plan_data,
        schedule,
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
                prerequisites = provisional[code]["prerequisites"]
                note = (
                    f"PROVISIONAL: estimated {PROVISIONAL_CREDITS} credits; "
                    "not in CPSC catalog; "
                    + (f"study-plan prerequisites: {prerequisites}"
                       if prerequisites else "no prerequisites listed in study plan")
                )
                existing = course.get("notes", "")
                course["notes"] = existing + "; " + note if existing else note

    result["track"] = study_plan["track"]
    result["start_semester"] = start_semester
    result["required_courses"] = study_plan["required_courses"]
    result["provisional_courses"] = provisional
    result["warnings"] = (
        study_plan["warnings"]
        + offering_warnings
        + catalog_warnings
        + template_prerequisite_conflicts(study_plan, catalog)
        + result["warnings"]
    )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate a semester-by-semester course plan."
    )
    parser.add_argument("--track", choices=list(TRACKS), default="general")
    parser.add_argument("--start", default="Spring 2027",
                        help="Starting semester, e.g. 'Spring 2027'.")
    parser.add_argument("--max-credits", type=int, default=12)
    parser.add_argument("--no-summer", action="store_true")
    parser.add_argument("--study-plans", type=Path, default=DEFAULT_STUDY_PLANS)
    parser.add_argument("--degreeworks", type=Path, default=DEFAULT_DEGREEWORKS)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional JSON output path.")
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
        credits = sum(course["credits"] for course in semester["courses"])
        print(f"{semester['semester']} ({credits} credits)")
        for course in semester["courses"]:
            scheduled_count += 1
            print(f"  {course['course_code']} - {course['title']}")
            if course.get("notes"):
                print(f"    NOTE: {course['notes']}")

    if scheduled_count == 0:
        print("No additional courses scheduled.")

    print()
    print("UNSCHEDULED COURSES")
    print("-" * 50)
    if result["unscheduled"]:
        for course in result["unscheduled"]:
            print(f"{course['course_code']}: {course['reason']}")
    else:
        print("None")

    if result["warnings"]:
        print()
        print("WARNINGS")
        print("-" * 50)
        for warning in result["warnings"]:
            print("-", warning)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as file:
            json.dump(result, file, indent=2)
        print()
        print("JSON saved to:", args.output)


if __name__ == "__main__":
    main()
