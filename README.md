# Smart Class Planning Tool for Academic Advising

A Python-based academic planning project for Columbus State University.

The tool uses student progress, graduate study plans, course catalog data,
and course offerings to recommend semester-by-semester academic plans.

## Requirements

- Python 3.12 or newer
- Dependencies from requirements.txt

## Installation

Clone the repository:

    git clone https://github.com/blizzard-edge/Academic_Planning_Tool.git
    cd Academic_Planning_Tool

Create a virtual environment:

    python -m venv .venv

Activate it on Windows:

    .\.venv\Scripts\Activate.ps1

Install dependencies:

    python -m pip install -r requirements.txt

## Required Data

The planning workflow uses these files:

- data/Graduate_Study_Plans.xlsx
- data/4_year_schedule.xlsx
- data/cpsc_course_catalog.json
- data/degree_works_info.json

The DegreeWorks JSON contains student information and must remain local.
It is excluded from Git tracking.

## Prepare Student Data

Export your DegreeWorks audit as a PDF, then run:

    python src/DegreeWorksParser.py "path\to\your_degreeworks.pdf"

This creates `data/degree_works_info.json`, which stays local and is
excluded from Git. Use only your own or authorized student records.

Optional: refresh the course catalog:

    python src/CourseCatalogRetriever.py
## Run the Course Planner

The course planner is currently developed in PR #4 on the
feature/course-planner branch. It becomes available on main after merging.

Generate a Software Development plan:

    python src/CoursePlannerIntegration.py --track software --start "Spring 2027"

Other supported ACS tracks:

- ai
- general

Save a plan to JSON:

    python src/CoursePlannerIntegration.py --track software --start "Spring 2027" --output outputs/recommended_plan.json

## Export to Excel

    python src/CoursePlanExporter.py outputs/recommended_plan.json outputs/recommended_plan.xlsx

Note: The exporter is still undergoing integration testing. Verify
that all semesters appear in the exported workbook.

## Privacy and Academic Advising

Do not commit student records or personally identifying information.

Course recommendations may include provisional credits or conditional
prerequisites. Confirm academic requirements with an advisor.
