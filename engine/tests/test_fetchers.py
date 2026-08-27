import unittest

from engine.fetchers.starling import StarlingFetcher
from engine.fetchers.wiktionary import WiktionaryFetcher


class TestFetchers(unittest.TestCase):
    def test_starling_offline_lexicon(self):
        fetcher = StarlingFetcher()
        result = fetcher.fetch("su")
        self.assertEqual(result["root"]["proto_turkic"], "*sub")
        self.assertTrue(len(result["turkic_languages"]) > 5)

        # Dil isimleri ve kodları doğrulaması
        lang_codes = [e["lang_code"] for e in result["turkic_languages"]]
        self.assertIn("otk", lang_codes)
        self.assertIn("tr", lang_codes)
        self.assertIn("az", lang_codes)
        self.assertIn("kk", lang_codes)

    def test_wiktionary_fetcher_parse(self):
        fetcher = WiktionaryFetcher()
        test_wikitext = """
* Common Turkic:
** {{desc|tr|su}}
** {{desc|az|su}}
** {{desc|kk|су}}
** {{desc|cv|шыв}}
        """
        result = {"root": {"meaning": "water"}, "turkic_languages": []}
        fetcher._parse_reconstruction_page(test_wikitext, result)
        self.assertEqual(len(result["turkic_languages"]), 4)
        langs = {item["lang_code"]: item["word"] for item in result["turkic_languages"]}
        self.assertEqual(langs["tr"], "su")
        self.assertEqual(langs["cv"], "шыв")

if __name__ == "__main__":
    unittest.main()
