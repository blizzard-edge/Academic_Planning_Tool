"""Tests for the DegreeWorks text parser.

The audits are synthetic text in the layout pypdf extracts from real
DegreeWorks PDFs; no student's file or personal data is used.

Run from the project root:

    python -m unittest discover -s test -v
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from DegreeWorksParser import parse_courses  # noqa: E402


def codes(result, key):
    return sorted(course["course_code"] for course in result[key])


# Layout of an audit where every requirement is met or in progress.
NEARLY_DONE_AUDIT = """Area 1
CPSC 6109- Algorithms Analysis and DesignCPSC 6109 Algorithms Analysis and Design A 3 Spring 2025
CPSC 6119- Object-Oriented Development CPSC 6119 Obj-Orient Dev w/Components A 3 Fall 2025
CYBR 6126- Intro to Cybersecurity CYBR 6126 Introduction to Cybersecurity A 3 Fall 2024
CPSC 6185- Intelligent Systems CPSC 6185 Intelligent Systems A 3 Spring 2025
Program Electives CPSC 6555 Selected Topics in CS A 3 Summer 2025
Exit Exam CPSC 6000 Graduate Exit Exam in CS CURR (0) Fall 2026
Area 2
CPSC 6125-Operating Systems Design and CPSC 6125 Op Sys Design & Implement CURR (3) Fall 2026
Implementation
CPSC 6127- Contemporaray Issues in DBMS CPSC 6127 Contmpry Is In DB Man Sys A 3 Spring 2026
CPSC 6177- Software Design and Developemnt CPSC 6177 Software Design, Development CURR (3) Fall 2026
Notes
Description Created on Created by
Student was advised for upcoming semester. Take CPSC 6109 CPSC 6185 10/17/2024 Advisor
Legend
"""

# Reproduces the three problems reported on a second audit: a wrapped
# label that shares a line with another course's record, a title that
# wraps onto the next line, and advisor notes written as "Fall 2025 - ...".
WRAPPED_LABEL_AUDIT = """Area 2
CPSC 6109- Algorithms Analysis and Design CPSC 6109 Algorithms Analysis and Design CURR (3) Fall 2026
CPSC 6179- Software Project Planning and
CPSC 6175- Web Engineering and Technologies CPSC 6177 Software Design, Development CURR (3) Fall 2026
Management Still needed: 1 Class in CPSC 6179
CPSC 6119- Object-Oriented Development CPSC 6119 Obj-Orient Dev w/Components A 3 Fall 2025
In-progress
CPSC 6109 Algorithms Analysis and Design CURR (3) Fall 2026
CPSC 6177 Software Design, Development CURR (3) Fall 2026
Notes
Description Created on Created by
Fall 2025 - CPSC 6119, CPSC 6125
Fall 2206 - CPSC 6109, CYBR 6159 (elective), CPSC 6177 Spring 2027 - CYBR 6127 (elective), CPSC 6185,
Legend
"""


class TestNearlyDoneAudit(unittest.TestCase):
    def setUp(self):
        self.result = parse_courses(NEARLY_DONE_AUDIT)

    def test_completed(self):
        self.assertEqual(
            codes(self.result, "completed_courses"),
            ["CPSC 6109", "CPSC 6119", "CPSC 6127", "CPSC 6185", "CPSC 6555", "CYBR 6126"],
        )

    def test_in_progress(self):
        self.assertEqual(
            codes(self.result, "in_progress_courses"),
            ["CPSC 6000", "CPSC 6125", "CPSC 6177"],
        )

    def test_nothing_remaining(self):
        self.assertEqual(codes(self.result, "remaining_courses"), [])

    def test_course_code_joined_to_previous_word_is_found(self):
        # pypdf can join columns without a space: "DesignCPSC 6109".
        self.assertIn("CPSC 6109", codes(self.result, "completed_courses"))


class TestWrappedLabelAudit(unittest.TestCase):
    def setUp(self):
        self.result = parse_courses(WRAPPED_LABEL_AUDIT)

    def test_in_progress_credit_goes_to_the_course_record_not_the_label(self):
        in_progress = codes(self.result, "in_progress_courses")
        self.assertEqual(in_progress, ["CPSC 6109", "CPSC 6177"])
        self.assertNotIn("CPSC 6175", in_progress)

    def test_still_needed_line_does_not_steal_next_lines_grade(self):
        # "... Class in CPSC 6179" is followed by CPSC 6119's real record.
        completed = codes(self.result, "completed_courses")
        self.assertEqual(completed, ["CPSC 6119"])
        self.assertNotIn("CPSC 6119", codes(self.result, "remaining_courses"))

    def test_label_only_courses_are_remaining(self):
        self.assertEqual(codes(self.result, "remaining_courses"), ["CPSC 6175", "CPSC 6179"])

    def test_wrapped_title_is_joined(self):
        titles = {c["course_code"]: c["title"] for c in self.result["remaining_courses"]}
        self.assertEqual(titles["CPSC 6179"], "Software Project Planning and Management")
        self.assertEqual(titles["CPSC 6175"], "Web Engineering and Technologies")

    def test_advisor_notes_are_not_requirements(self):
        remaining = codes(self.result, "remaining_courses")
        self.assertFalse([code for code in remaining if code.startswith("FALL")])

    def test_season_words_never_become_course_codes(self):
        text = "FALL 2025 - CPSC 6119\nFall 2206 - CPSC 6109\n"
        result = parse_courses(text)
        self.assertEqual(codes(result, "remaining_courses"), [])


class TestGrades(unittest.TestCase):
    def test_plus_minus_grades_and_suffix_codes(self):
        result = parse_courses(
            "CPSC 6119 Obj-Orient Dev B+ 3 Fall 2025\n"
            "CPSC 1302K Computer Science II A- 4 Fall 2024\n"
        )
        grades = {c["course_code"]: c["grade"] for c in result["completed_courses"]}
        self.assertEqual(grades, {"CPSC 6119": "B+", "CPSC 1302K": "A-"})


if __name__ == "__main__":
    unittest.main()
