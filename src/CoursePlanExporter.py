"""
SCPTAA_010 - Course Plan Excel Output

Exports a recommended course plan to a readable Excel workbook.

Expected input JSON can be either:
  1. A list of semester entries, or
  2. The object written by CourseOfferingValidator.py, containing a "plan" list.

Example:
[
  {
    "semester": "Fall 2026",
    "courses": [
      {"course_code": "CPSC 1302K", "title": "Example Course", "credits": 4}
    ]
  }
]

Install dependency:
    pip install openpyxl
"""

import json
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = ["Course Code", "Course Title", "Credits", "Notes"]

def normalize_plan(data):
    """Accept a raw semester list or a validator result object."""
    if isinstance(data, dict):
        data = data.get("plan")
    if not isinstance(data, list):
        raise ValueError(
            "Plan JSON must be a list of semester entries or an object with a 'plan' list."
        )

    for index, semester in enumerate(data):
        if not isinstance(semester, dict):
            raise ValueError(f"Semester entry {index + 1} must be an object.")
        if not isinstance(semester.get("semester"), str):
            raise ValueError(f"Semester entry {index + 1} needs a semester name.")
        if not isinstance(semester.get("courses"), list):
            raise ValueError(
                f"Semester '{semester['semester']}' must contain a courses list."
            )
        for course in semester["courses"]:
            if not isinstance(course, dict) or not course.get("course_code"):
                raise ValueError(
                    f"Every course in '{semester['semester']}' needs a course_code."
                )
    return data

def export_course_plan(plan, output_path):
    """Write one worksheet with courses grouped by semester."""
    plan = normalize_plan(plan)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Recommended Plan"

    sheet.append(["Recommended Course Plan"])
    sheet["A1"].font = Font(bold=True, size=16)
    sheet.append(["Semester", "Course Code", "Course Title", "Credits", "Notes"])
    for cell in sheet[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(horizontal="center")

    for semester_entry in plan:
        semester = semester_entry["semester"]
        courses = semester_entry["courses"]

        if not courses:
            sheet.append([semester, "", "(No courses assigned)", "", ""])
            continue

        for course in courses:
            credits = course.get("credits", course.get("course_hours", ""))
            notes = course.get("notes", "")
            sheet.append([
                semester,
                course["course_code"],
                course.get("title", ""),
                credits,
                notes
            ])

    # Add filters, freeze the column headers, and make the workbook readable.
    sheet.auto_filter.ref = f"A2:E{max(sheet.max_row, 2)}"
    sheet.freeze_panes = "A3"
    widths = {1: 20, 2: 18, 3: 48, 4: 12, 5: 36}
    for column, width in widths.items():
        sheet.column_dimensions[get_column_letter(column)].width = width

    for row in sheet.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    workbook.save(output_path)
    return output_path

def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python src/CoursePlanExporter.py "
            "<recommended_plan.json> <output.xlsx>"
        )
        sys.exit(1)

    input_path, output_path = sys.argv[1:3]
    try:
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Recommended plan not found: {input_path}")
        with open(input_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        export_course_plan(data, output_path)
        print(f"Excel course plan saved to {output_path}")

    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not export course plan: {error}")
        sys.exit(1)

if __name__ == "__main__":
    main()