import unittest

from london_property_analysis.ppd import is_london_row, yearly_url


class PricePaidDataTests(unittest.TestCase):
    def test_yearly_url_uses_land_registry_public_bucket(self):
        self.assertTrue(yearly_url(2025).endswith("/pp-2025.csv"))

    def test_london_filter_accepts_target_district(self):
        row = {
            "district": "KENSINGTON AND CHELSEA",
            "county": "",
            "town_city": "",
        }

        self.assertTrue(is_london_row(row))

    def test_london_filter_accepts_london_town(self):
        row = {
            "district": "",
            "county": "",
            "town_city": "LONDON",
        }

        self.assertTrue(is_london_row(row))


if __name__ == "__main__":
    unittest.main()
