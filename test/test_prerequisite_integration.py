"""Check that semester planning really delegates prerequisite evaluation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import CoursePlanner
import PrerequisiteChecker


class TestPrerequisiteModuleIntegration(unittest.TestCase):
    def test_planner_uses_dedicated_checker(self):
        catalog = [{
            "course_code": "CPSC 6109",
            "title": "Algorithms Analysis and Design",
            "credits": 3,
            "prerequisites": "CPSC 6185",
        }]
        audit = {
            "completed_courses": [{"course_code": "CPSC 6185", "grade": "A"}],
            "in_progress_courses": [],
        }
        with patch.object(
            PrerequisiteChecker, "_evaluate_requirements",
            wraps=PrerequisiteChecker._evaluate_requirements
        ) as evaluate:
            result = CoursePlanner.build_course_plan(
                required_courses=["CPSC 6109"],
                degreeworks_data=audit,
                course_catalog=catalog,
                offering_schedule={"CPSC 6109": ["Spring 2027"]},
                start_semester="Spring 2027",
            )
        self.assertGreater(evaluate.call_count, 0)
        self.assertEqual(result["unscheduled"], [])
        self.assertTrue(any(
            course["course_code"] == "CPSC 6109"
            for term in result["plan"] for course in term["courses"]
        ))


if __name__ == "__main__":
    unittest.main()
