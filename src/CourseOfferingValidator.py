"""
SCPTAA_008 - Course Offering Validation

Checks a recommended course plan against a four-year offering schedule.
When a course is unavailable in its assigned semester, the validator tries
later semesters in the plan and moves it to the first available valid semester.

Expected offering schedule JSON:
{
  "CPSC 1302K": ["Fall", "Spring"],
  "CPSC 6125": ["Fall 2026", "Fall 2027"]
}

Expected plan structure:
[
  {
    "semester": "Fall 2026",
    "courses": [
      {"course_code": "CPSC 1302K", "title": "Example", "credits": 3}
    ]
  }
]

This module does not infer prerequisites or create additional semesters. If no
later planned semester is available, it reports a conflict for advisor review.
"""

import json
import os
import sys

def season_of(term):
    """Return normalized season from 'Fall 2026' or 'Fall'."""
    if not isinstance(term, str) or not term.strip():
        return ""
    return term.strip().split()[0].lower()

def is_offered(course_code, semester, offering_schedule):
    """Return whether a course is offered in the specified semester."""
    terms = offering_schedule.get(course_code)
    if not isinstance(terms, list):
        return False

    target_season = season_of(semester)
    for term in terms:
        if not isinstance(term, str):
            continue
        # A season-only entry (e.g. 'Fall') applies to every year.
        if term.strip().lower() == target_season:
            return True
        # A full-term entry (e.g. 'Fall 2026') must match the full term.
        if term.strip().lower() == semester.strip().lower():
            return True
    return False

def validate_and_adjust_plan(plan, offering_schedule):
    """
    Validate and, where possible, adjust course semesters.

    Returns:
        adjusted_plan: plan with movable courses reassigned
        conflicts: list of unresolved course availability conflicts
        adjustments: list describing semester changes
    """
    if not isinstance(plan, list):
        raise ValueError("The recommended plan must be a list of semesters.")
    if not isinstance(offering_schedule, dict):
        raise ValueError("The offering schedule must be a dictionary.")

    adjusted_plan = []
    for semester_entry in plan:
        if not isinstance(semester_entry, dict):
            raise ValueError("Each semester entry must be an object.")
        if not isinstance(semester_entry.get("semester"), str):
            raise ValueError("Each semester entry needs a semester string.")
        if not isinstance(semester_entry.get("courses"), list):
            raise ValueError(
                f"{semester_entry.get('semester')}: courses must be a list."
            )
        adjusted_plan.append({
            **semester_entry,
            "courses": list(semester_entry["courses"])
        })

    conflicts = []
    adjustments = []

    for index, semester_entry in enumerate(adjusted_plan):
        current_semester = semester_entry["semester"]
        remaining_courses = []

        for course in semester_entry["courses"]:
            if not isinstance(course, dict) or not course.get("course_code"):
                conflicts.append({
                    "course_code": "UNKNOWN",
                    "semester": current_semester,
                    "reason": "Course entry is missing a course_code."
                })
                continue

            code = course["course_code"].strip()
            if is_offered(code, current_semester, offering_schedule):
                remaining_courses.append(course)
                continue

            destination = None
            for later_index in range(index + 1, len(adjusted_plan)):
                later_semester = adjusted_plan[later_index]["semester"]
                if is_offered(code, later_semester, offering_schedule):
                    destination = later_index
                    break

            if destination is None:
                conflicts.append({
                    "course_code": code,
                    "semester": current_semester,
                    "reason": (
                        "Course is not offered in the assigned semester and no "
                        "later available semester exists in the supplied plan."
                    )
                })
                # Keep the course in the plan so it is not silently lost.
                remaining_courses.append(course)
            else:
                destination_semester = adjusted_plan[destination]["semester"]
                adjusted_plan[destination]["courses"].append(course)
                adjustments.append({
                    "course_code": code,
                    "from_semester": current_semester,
                    "to_semester": destination_semester
                })

        semester_entry["courses"] = remaining_courses

    # Remove empty semesters only if they were empty in the original plan too;
    # preserve the user's intended semester structure.
    return adjusted_plan, conflicts, adjustments

def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python src/CourseOfferingValidator.py "
            "<recommended_plan.json> <course_offerings.json> <output_plan.json>"
        )
        sys.exit(1)

    plan_path, offerings_path, output_path = sys.argv[1:4]

    try:
        for path, label in (
            (plan_path, "Recommended plan"),
            (offerings_path, "Offering schedule"),
        ):
            if not os.path.isfile(path):
                raise FileNotFoundError(f"{label} file not found: {path}")

        with open(plan_path, "r", encoding="utf-8") as file:
            plan = json.load(file)
        with open(offerings_path, "r", encoding="utf-8") as file:
            offerings = json.load(file)

        adjusted, conflicts, adjustments = validate_and_adjust_plan(plan, offerings)

        output = {
            "plan": adjusted,
            "adjustments": adjustments,
            "conflicts": conflicts
        }
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(output, file, indent=4, ensure_ascii=False)

        print(f"Saved validated plan to {output_path}")
        for adjustment in adjustments:
            print(
                f"Moved {adjustment['course_code']}: "
                f"{adjustment['from_semester']} -> {adjustment['to_semester']}"
            )
        for conflict in conflicts:
            print(
                f"CONFLICT: {conflict['course_code']} in {conflict['semester']}: "
                f"{conflict['reason']}"
            )
        if conflicts:
            print(f"Validation completed with {len(conflicts)} unresolved conflict(s).")
            sys.exit(2)
        print("Validation completed without conflicts.")
        sys.exit(0)

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Error parsing JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()