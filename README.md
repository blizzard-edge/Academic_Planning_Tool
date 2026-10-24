# Smart Class Planning Tool for Academic Advising

CPSC 6177 - Software Design & Development
Columbus State University | Fall 2026

## Project Overview

The Smart Class Planning Tool is a Python-based academic advising project that generates semester-by-semester course recommendations.

It combines:
- A student's DegreeWorks academic audit
- Graduate Study Plan requirements
- The university's four-year course offering schedule
- Course descriptions and prerequisites from the CSU CPSC catalog

The resulting course plan can be exported to an Excel workbook.

## Current Implementation

The project includes:

- DegreeWorks PDF parsing and course classification
- Graduate Study Plan parsing
- Four-year course schedule parsing
- CPSC course catalog retrieval
- Prerequisite checking
- Semester-by-semester course planning
- Course offering and input validation
- Excel course plan export

The current working workflow uses command-line modules. A unified application controller in `src/Main.py` has not yet been implemented.

## Requirements

- Python 3.12 or newer
- Windows with PowerShell for the commands below
- Dependencies listed in `requirements.txt`

## Installation

Clone the repository:

```powershell
git clone https://github.com/blizzard-edge/Academic_Planning_Tool.git
cd Academic_Planning_Tool

```

Create and activate a virtual environment on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Project Data

The repository includes:

- `data/Graduate_Study_Plans.xlsx`
- `data/4_year_schedule.xlsx`
- `data/cpsc_course_catalog.json`

Student DegreeWorks information is not included in GitHub because it may contain personally identifying information.

## Prepare Student Data

Export an authorized DegreeWorks audit as a PDF and run:

```powershell
python src/DegreeWorksParser.py "path\to\degreeworks.pdf"
```

This generates `data/degree_works_info.json`, which is excluded from Git tracking.

The planner also accepts another compatible DegreeWorks JSON file through the `--degreeworks` argument.

## Generate a Course Plan

Example: Software Development track, starting Spring 2027:

```powershell
python src/CoursePlannerIntegration.py --track software --start "Spring 2027" --max-credits 12 --output outputs/recommended_plan.json
```

Supported track arguments:

| Argument | Graduate study plan |
|---|---|
| `software` | ACS - Software Development |
| `general` | ACS - General |
| `ai` | ACS - AI and Data Science |
| `cyber-defense` | CYBR - Cyber Defense |
| `cyber-management` | CYBR - Management |

The planner considers course availability, prerequisites, previously completed courses, courses in progress, and semester credit limits.

Use `--no-summer` to exclude summer semesters.

## Export to Excel

After generating the JSON plan, run:

```powershell
python src/CoursePlanExporter.py outputs/recommended_plan.json outputs/recommended_plan.xlsx
```

The resulting workbook contains the semester-by-semester course recommendations.

## Automated Testing

Run from the repository root:

```powershell
python -m unittest discover -s test -q
```

The current test suite contains 36 automated tests covering:

- DegreeWorks parsing and regression cases
- Semester planning and prerequisites
- Course offering schedules
- Credit limits and conditional requirements
- Study-plan and schedule-parser integration
- Input and course-offering validation

A separate new-student integration test successfully scheduled eight courses across four semesters, verified course availability and prerequisite results, and confirmed that all eight courses appeared in the Excel output.

Some automated tests require the university data files included in the repository.

## Known Limitations

- The working workflow uses command-line modules. A unified controller in `src/Main.py` has not yet been implemented.
- Some CYBR courses are absent from the CPSC catalog; provisional information is flagged for advisor verification.
- Elective and MSOL placeholders are not automatically converted into specific courses.
- The scheduling algorithm is not guaranteed to produce the shortest graduation path.
- Concurrent enrollment and certain prerequisite relationships may require advisor approval.
- Additional DegreeWorks PDF layouts still need testing.
- The current-semester reference is fixed at Fall 2026.

## Privacy

Do not commit personal academic records, student identifiers, or private DegreeWorks files.

The standard local DegreeWorks JSON output is excluded through `.gitignore`.

## Academic Advising Disclaimer

Generated recommendations are planning aids, not official graduation approvals. Students should verify requirements, prerequisites, and availability with their academic advisors.
