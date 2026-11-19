import unittest

from scripts.build_inventory import merge_source_records


class SourceUnionTests(unittest.TestCase):
    def test_wikipedia_sitelink_crosswalk_merges_distinct_labels(self):
        groups, unresolved = merge_source_records(
            [{"id": "c-plus-plus", "name": "C++", "wikipedia": "https://en.wikipedia.org/wiki/C%2B%2B"}],
            [{"id": "Q2407", "name": "C plus plus", "enwiki": "C++"}],
            [],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0]["sources"]), {"pldb", "wikidata"})
        self.assertIn("exact-wikipedia-sitelink", {row["method"] for row in groups[0]["matches"]})
        self.assertEqual(unresolved, [])

    def test_published_alias_merges_only_when_unique(self):
        groups, _ = merge_source_records(
            [{"id": "golang", "name": "Go", "aka": "golang", "githubLanguage": "Go"}],
            [],
            [{"name": "Go", "aliases": ["golang"], "language_id": 87}],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0]["sources"]), {"pldb", "github_linguist"})
        self.assertIn("pldb-githubLanguage", {row["method"] for row in groups[0]["matches"]})

    def test_ambiguous_exact_name_is_left_unmerged(self):
        groups, unresolved = merge_source_records(
            [{"id": "x-one", "name": "X One"}],
            [{"id": "Q1", "name": "X One"}, {"id": "Q2", "name": "X One"}],
            [],
        )
        self.assertEqual(len(groups), 3)
        self.assertTrue(any(row["reason"] == "ambiguous-exact-name" for row in unresolved))

    def test_canonical_ids_are_stable(self):
        groups, _ = merge_source_records(
            [{"id": "python", "name": "Python"}],
            [{"id": "Q28865", "name": "Python"}],
            [{"name": "Python", "aliases": [], "language_id": 303}],
        )
        self.assertEqual(groups[0]["id"], "wikidata:Q28865")


if __name__ == "__main__":
    unittest.main()
