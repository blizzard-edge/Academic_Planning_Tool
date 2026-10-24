"""Regression tests for DegreeWorks input structure."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from CoursePlanner import build_course_plan


def run_planner(student):
    return build_course_plan(
        required_courses=[],
        degreeworks_data=student,
        course_catalog=[],
        offering_schedule={},
        start_semester="Spring 2027",
    )


class TestDegreeWorksInputValidation(unittest.TestCase):
    def test_rejects_exported_course_plan(self):
        with self.assertRaisesRegex(ValueError, "Invalid DegreeWorks data"):
            run_planner({"plan": [], "unscheduled": [], "warnings": []})

    def test_rejects_missing_in_progress_field(self):
        with self.assertRaisesRegex(ValueError, "in_progress_courses"):
            run_planner({"completed_courses": []})

    def test_rejects_non_list_field(self):
        with self.assertRaisesRegex(ValueError, "must be a list"):
            run_planner({
                "completed_courses": {},
                "in_progress_courses": [],
            })

    def test_accepts_valid_new_student_structure(self):
        result = run_planner({
            "completed_courses": [],
            "in_progress_courses": [],
            "remaining_courses": [],
        })
        self.assertEqual(result["unscheduled"], [])


if __name__ == "__main__":
    unittest.main()
