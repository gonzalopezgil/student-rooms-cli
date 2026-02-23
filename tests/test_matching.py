import unittest

from matching import match_semester1
from models.config import AcademicYearConfig, Semester1Rules


class TestSemester1Matching(unittest.TestCase):
    def test_semester1_match(self):
        config = AcademicYearConfig(
            start_year=2024,
            end_year=2025,
            semester1=Semester1Rules(name_keywords=["semester 1"], require_keyword=True),
        )
        option = {
            "fromYear": 2024,
            "toYear": 2025,
            "tenancyOption": [
                {
                    "name": "Semester 1",
                    "formattedLabel": "Semester 1 (Fall)",
                }
            ],
        }
        self.assertTrue(match_semester1(option, config))

    def test_semester1_mismatch_year(self):
        config = AcademicYearConfig(
            start_year=2024,
            end_year=2025,
            semester1=Semester1Rules(name_keywords=["semester 1"], require_keyword=True),
        )
        option = {
            "fromYear": 2023,
            "toYear": 2024,
            "tenancyOption": [
                {
                    "name": "Semester 1",
                    "formattedLabel": "Semester 1",
                }
            ],
        }
        self.assertFalse(match_semester1(option, config))


if __name__ == "__main__":
    unittest.main()
