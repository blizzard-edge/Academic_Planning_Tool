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

def main(parsed_course_catalog, course_plan):
    return validate_course_plan(parsed_course_catalog, course_plan)

if __name__ == "__main__":
    with open("../data/cpsc_course_catalog.json", "r") as file:
        parsed_course_catalog = json.load(file)

    with open("../test/test_prereq_checker.json", "r") as file:
        course_plan = json.load(file)
    print(main(parsed_course_catalog, course_plan))