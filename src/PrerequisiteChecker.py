import re
import json


# Use pattern matching to identify necessary prereqs, including AND / OR
# Return arr [[interchangeable courses], [additional interchangeable necessary courses]]
def parse_prerequisite_property(prerequisite_string):
    parsed_prerequisites = []

    # Split string on "and" to separate courses that are not interchangeable
    groups = re.split(r"\band\b", prerequisite_string)

    # Iterate through each group of interchangeable courses, adding each course to above array
    for group in groups:
        courses = re.findall(r'[A-Z]{4}\s[0-9]{4}[A-Z]?', group)

        # Normalize courses to prevent whitespace or line breaks from breaking the comparisons
        courses = [course.replace("\xa0", " ").strip() for course in courses]
        parsed_prerequisites.append(courses)
    return parsed_prerequisites

# Extracts prerequisites for each course that requires them from course catalog json file
def extract_prerequisites(course_catalog):
    prerequisites_dict = {}
    # Iterate through json file
    for course in course_catalog:
        if course.get("prerequisites"):
            # Add prerequisites for that course to dict
            prerequisites_dict[course.get("course_code")] = parse_prerequisite_property(course.get("prerequisites"))
    return prerequisites_dict

# Checks if any prerequisite has been completed in a single array (courses where only ONE needs to be completed are in single array)
def prerequisite_group_satisfied(prereq_arr, course_plan):

    for prereq in prereq_arr:
        if prereq in [course_code.replace("\xa0", " ").strip() for course_code in course_plan.get("courses")]:
            return True
    return False


# Returns dictionary of courses with values of an array of remaining prerequisites.
def find_unmet_prerequisites(prerequisites, course_plan):
    # Dict of course: [remaining prereqs]
    overall_unmet_prerequisites = {}

    # Add any unmet prerequisites to the above dict. Normalize course codes in course_plan so whitespace or line breaks don't mess things up
    for course_code in [course_code.replace("\xa0", " ").strip() for course_code in course_plan.get("courses")]:
        if prerequisites.get(course_code):
            course_unmet_prerequisites = []
            for arr in prerequisites[course_code]:
                if prerequisite_group_satisfied(arr, course_plan):
                    continue
                else:
                    # Appends group of prereqs (each single array is OR group - only one course needs to be done)
                    course_unmet_prerequisites.append(arr)
            if course_unmet_prerequisites:
                overall_unmet_prerequisites[course_code] = course_unmet_prerequisites

    return overall_unmet_prerequisites

# Returns dict of unmet prerequisites or empty dict or course plan is valid
def validate_course_plan(parsed_course_catalog, course_plan):
    prerequisites = extract_prerequisites(parsed_course_catalog)
    prerequisites_still_required = find_unmet_prerequisites(prerequisites, course_plan)

    return prerequisites_still_required



# Advanced prerequisite evaluation shared by the course scheduler.
TOKEN_PATTERN = re.compile(
    r"\s*(?:"
    r"(?P<course>[A-Z]{4}\s+\d{4}[A-Z]?)"
    r"|(?P<operator>AND|OR)\b"
    r"|(?P<paren>[()])"
    r")",
    re.IGNORECASE,
)
GRADE_PATTERN = re.compile(
    r"\s+WITH\s+A\s+MINIMUM\s+GRADE\s+OF\s+([A-DF])\b",
    re.IGNORECASE,
)
CONCURRENT_PATTERN = re.compile(
    r"\s*\(\s*MAY\s+BE\s+TAKEN\s+CONCURRENTLY\s*\)",
    re.IGNORECASE,
)
GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


class UnsupportedPrerequisiteError(ValueError):
    """An academic requirement cannot be interpreted safely."""


def normalize_course_code(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\u00c2", "").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip().upper()


def normalize_course_list(courses):
    result = set()
    for course in courses or []:
        value = course.get("course_code") if isinstance(course, dict) else course
        code = normalize_course_code(value)
        if code:
            result.add(code)
    return result


def tokenize_prerequisites(text):
    """Tokenize boolean course requirements; reject unsupported words."""
    text = normalize_course_code(text)
    tokens = []
    position = 0
    while position < len(text):
        if text[position:].isspace():
            break
        match = TOKEN_PATTERN.match(text, position)
        if not match:
            raise UnsupportedPrerequisiteError(
                f"Unsupported prerequisite language near {text[position:position + 50]!r}"
            )
        if match.group("course"):
            tokens.append(("COURSE", normalize_course_code(match.group("course"))))
        elif match.group("operator"):
            operator = match.group("operator").upper()
            tokens.append((operator, operator))
        else:
            symbol = match.group("paren")
            tokens.append((symbol, symbol))
        position = match.end()
    return tokens


class PrerequisiteExpressionParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def peek(self):
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position][0]

    def consume(self, expected):
        if self.peek() != expected:
            raise UnsupportedPrerequisiteError(
                f"Expected {expected}, found {self.peek()}."
            )
        value = self.tokens[self.position][1]
        self.position += 1
        return value

    def parse(self):
        if not self.tokens:
            return None
        expression = self.parse_or()
        if self.peek() is not None:
            raise UnsupportedPrerequisiteError("Unexpected trailing prerequisite.")
        return expression

    def parse_or(self):
        left = self.parse_and()
        while self.peek() == "OR":
            self.consume("OR")
            left = ("OR", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_atom()
        while self.peek() == "AND":
            self.consume("AND")
            left = ("AND", left, self.parse_atom())
        return left

    def parse_atom(self):
        if self.peek() == "COURSE":
            return ("COURSE", self.consume("COURSE"))
        if self.peek() == "(":
            self.consume("(")
            expression = self.parse_or()
            self.consume(")")
            return expression
        raise UnsupportedPrerequisiteError(
            f"Expected course or opening parenthesis, found {self.peek()}."
        )


def parse_prerequisite_details(prerequisite_text):
    """Return parsed requirements, minimum grades, and concurrency notes.

    Minimum-grade and concurrency language is recognized, but not
    silently treated as proof that those conditions were satisfied.
    """
    if prerequisite_text is None or prerequisite_text == "":
        return None, {}, set()

    if not isinstance(prerequisite_text, str):
        raise UnsupportedPrerequisiteError("Prerequisites must be text.")

    text = normalize_course_code(prerequisite_text)
    minimum_grades = {}
    concurrent = set()

    # Preserve grade requirements before removing catalog prose.
    for match in re.finditer(
        r"([A-Z]{4}\s+\d{4}[A-Z]?)"
        r"\s+WITH\s+A\s+MINIMUM\s+GRADE\s+OF\s+([A-DF])\b",
        text,
    ):
        minimum_grades[normalize_course_code(match.group(1))] = match.group(2)

    # Record courses explicitly marked as eligible for concurrency.
    for match in re.finditer(
        r"([A-Z]{4}\s+\d{4}[A-Z]?)"
        r"\s*\(\s*MAY\s+BE\s+TAKEN\s+CONCURRENTLY\s*\)",
        text,
    ):
        concurrent.add(normalize_course_code(match.group(1)))

    cleaned = GRADE_PATTERN.sub("", text)
    cleaned = CONCURRENT_PATTERN.sub("", cleaned)

    # Any other prose remains and causes a review-required error.
    expression = PrerequisiteExpressionParser(
        tokenize_prerequisites(cleaned)
    ).parse()
    return expression, minimum_grades, concurrent


def parse_prerequisite_groups(prerequisite_text):
    """Compatibility interface for existing prerequisite tests."""
    expression, _, _ = parse_prerequisite_details(prerequisite_text)
    return expression


def prerequisites_satisfied(expression, completed_courses):
    completed = normalize_course_list(completed_courses)

    def evaluate(node):
        if node is None or node == []:
            return True
        if isinstance(node, list):
            return all(
                any(normalize_course_code(option) in completed for option in group)
                for group in node
            )
        if not isinstance(node, tuple):
            raise UnsupportedPrerequisiteError("Invalid prerequisite expression.")
        if node[0] == "COURSE":
            return node[1] in completed
        if node[0] == "AND":
            return evaluate(node[1]) and evaluate(node[2])
        if node[0] == "OR":
            return evaluate(node[1]) or evaluate(node[2])
        raise UnsupportedPrerequisiteError("Unknown prerequisite operator.")

    return evaluate(expression)


def _student_grades(records):
    """Read known letter grades without assuming missing grades are passes."""
    grades = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        code = normalize_course_code(record.get("course_code"))
        grade = str(record.get("grade") or "").strip().upper()
        if code and grade in GRADE_RANK:
            grades[code] = grade
    return grades


def _evaluate_requirements(
    expression,
    available,
    completed,
    in_progress,
    grades,
    minimum_grades,
    allow_expected,
):
    """Return (eligible, conditional notes), respecting AND/OR grouping."""

    def evaluate(node):
        if node is None:
            return True, []

        operator = node[0]
        if operator == "COURSE":
            code = node[1]
            if code not in available:
                return False, []

            notes = []
            if code in in_progress and code not in completed:
                if not allow_expected:
                    return False, []
                notes.append(f"Expected completion of {code} must be verified")

            minimum = minimum_grades.get(code)
            if minimum:
                actual = grades.get(code)
                if actual is None:
                    notes.append(f"Verify {code} earned at least grade {minimum}")
                elif GRADE_RANK[actual] < GRADE_RANK[minimum]:
                    return False, []

            return True, notes

        if operator == "AND":
            left_ok, left_notes = evaluate(node[1])
            right_ok, right_notes = evaluate(node[2])
            return left_ok and right_ok, left_notes + right_notes

        if operator == "OR":
            left_ok, left_notes = evaluate(node[1])
            right_ok, right_notes = evaluate(node[2])
            if left_ok and right_ok:
                return (True, left_notes) if len(left_notes) <= len(right_notes) else (
                    True, right_notes
                )
            if left_ok:
                return True, left_notes
            if right_ok:
                return True, right_notes
            return False, []

        raise UnsupportedPrerequisiteError("Unknown prerequisite operator.")

    return evaluate(expression)



def main(parsed_course_catalog, course_plan):
    return validate_course_plan(parsed_course_catalog, course_plan)

if __name__ == "__main__":
    with open("../data/cpsc_course_catalog.json", "r") as file:
        parsed_course_catalog = json.load(file)

    with open("../test/test_prereq_checker.json", "r") as file:
        course_plan = json.load(file)
    print(main(parsed_course_catalog, course_plan))