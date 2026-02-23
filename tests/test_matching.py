import unittest

from matching import match_semester1
from models.config import AcademicYearConfig, Semester1Rules


class TestSemester1Matching(unittest.TestCase):
    def _cfg(self):
        return AcademicYearConfig(
            start_year=2026,
            end_year=2027,
            semester1=Semester1Rules(
                name_keywords=["semester 1"],
                require_keyword=True,
                enforce_month_window=True,
                start_months=[9, 10],
                end_months=[1, 2],
            ),
        )

    def test_semester1_match(self):
        config = self._cfg()
        option = {
            "fromYear": 2026,
            "toYear": 2027,
            "tenancyOption": [
                {
                    "name": "Semester 1",
                    "formattedLabel": "Semester 1",
                    "startDate": "2026-09-15",
                    "endDate": "2027-01-20",
                }
            ],
        }
        self.assertTrue(match_semester1(option, config))

    def test_semester1_mismatch_year(self):
        config = self._cfg()
        option = {
            "fromYear": 2025,
            "toYear": 2026,
            "tenancyOption": [
                {
                    "name": "Semester 1",
                    "formattedLabel": "Semester 1",
                    "startDate": "2025-09-20",
                    "endDate": "2026-01-25",
                }
            ],
        }
        self.assertFalse(match_semester1(option, config))

    def test_semester1_mismatch_keyword(self):
        config = self._cfg()
        option = {
            "fromYear": 2026,
            "toYear": 2027,
            "tenancyOption": [
                {
                    "name": "41 Weeks",
                    "formattedLabel": "THU, 27 AUG 2026 - THU, 10 JUN 2027",
                    "startDate": "2026-08-27",
                    "endDate": "2027-06-10",
                }
            ],
        }
        self.assertFalse(match_semester1(option, config))

    def test_semester1_mismatch_month_window(self):
        config = self._cfg()
        option = {
            "fromYear": 2026,
            "toYear": 2027,
            "tenancyOption": [
                {
                    "name": "Semester 1",
                    "formattedLabel": "Semester 1",
                    "startDate": "2026-08-27",
                    "endDate": "2027-06-10",
                }
            ],
        }
        self.assertFalse(match_semester1(option, config))


if __name__ == "__main__":
    unittest.main()
