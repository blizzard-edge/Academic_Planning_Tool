import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from CourseOfferingValidator import validate_and_adjust_plan
from InputValidator import validate_catalog


class TestCourseOfferingValidator(unittest.TestCase):
    def setUp(self):
        self.offerings = {
            "CPSC 6109": ["Spring"],
            "CPSC 6175": ["Fall"],
        }

    def test_preserves_multiple_semesters(self):
        plan = [
            {"semester": "Spring 2027", "courses": [{"course_code": "CPSC 6109"}]},
            {"semester": "Fall 2027", "courses": [{"course_code": "CPSC 6175"}]},
        ]
        adjusted, conflicts, moves = validate_and_adjust_plan(plan, self.offerings)
        self.assertEqual(len(adjusted), 2)
        self.assertFalse(conflicts)
        self.assertFalse(moves)

    def test_moves_unavailable_course(self):
        plan = [
            {"semester": "Spring 2027", "courses": [{"course_code": "CPSC 6175"}]},
            {"semester": "Fall 2027", "courses": []},
        ]
        adjusted, conflicts, moves = validate_and_adjust_plan(plan, self.offerings)
        self.assertEqual(adjusted[0]["courses"], [])
        self.assertEqual(adjusted[1]["courses"][0]["course_code"], "CPSC 6175")
        self.assertEqual(len(moves), 1)
        self.assertFalse(conflicts)

    def test_reports_unavailable_course(self):
        plan = [
            {"semester": "Spring 2027", "courses": [{"course_code": "CPSC 9999"}]}
        ]
        adjusted, conflicts, moves = validate_and_adjust_plan(plan, self.offerings)
        self.assertEqual(len(conflicts), 1)
        self.assertFalse(moves)

    def test_does_not_modify_original_plan(self):
        plan = [
            {"semester": "Spring 2027", "courses": [{"course_code": "CPSC 6175"}]},
            {"semester": "Fall 2027", "courses": []},
        ]
        validate_and_adjust_plan(plan, self.offerings)
        self.assertEqual(plan[0]["courses"][0]["course_code"], "CPSC 6175")
        self.assertEqual(plan[1]["courses"], [])


class TestInputValidator(unittest.TestCase):
    def test_rejects_invalid_second_record(self):
        catalog = [
            {"course_code": "CPSC 6109", "title": "Algorithms"},
            {"course_code": "", "title": "Invalid course"},
        ]
        with self.assertRaises(ValueError):
            validate_catalog(catalog)

    def test_accepts_valid_catalog(self):
        catalog = [
            {"course_code": "CPSC 6109", "title": "Algorithms"},
            {"course_code": "CPSC 6175", "title": "Web Engineering"},
        ]
        self.assertTrue(validate_catalog(catalog))

    def test_rejects_empty_catalog(self):
        with self.assertRaises(ValueError):
            validate_catalog([])


if __name__ == "__main__":
    unittest.main()
