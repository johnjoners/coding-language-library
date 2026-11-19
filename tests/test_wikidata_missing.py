import unittest
from unittest.mock import patch

from scripts.build_inventory import fetch_wikidata


class WikidataMissingTests(unittest.TestCase):
    @patch("scripts.build_inventory.time.sleep")
    @patch("scripts.build_inventory.get_json")
    def test_missing_entity_ids_are_preserved_in_source_state(self, get_json, _sleep):
        get_json.return_value = ({"entities": {"Q137924569": {"missing": ""}}}, {}, {})

        rows, state = fetch_wikidata(["Q137924569"])

        self.assertEqual(rows, [])
        self.assertEqual(state["items"], 0)
        self.assertEqual(state["missing_ids"], ["Q137924569"])


if __name__ == "__main__":
    unittest.main()
