import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_dictionaries import (  # noqa: E402
    EXPECTED_LOCALES,
    extract_placeholders,
    validate_locales,
)


ENGLISH = {
    "plain": "Ready",
    "url": "See https://example.test/users/{userId}?q={query}",
    "icu": "{count, plural, =0 {No items} one {# item for {name}} other {# items for {name}}}",
    "doubleCurly": "Hello, {{displayName}}",
    "quoted": "Write '{notAPlaceholder}' literally",
}


class ValidateLocalesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "repo"
        self.source_dir = self.base / "external-english"
        self.root.mkdir()
        self.source_dir.mkdir()
        self._write_dictionary(self.source_dir / "home.json", ENGLISH)
        for locale in EXPECTED_LOCALES:
            locale_dir = self.root / locale
            locale_dir.mkdir()
            self._write_dictionary(locale_dir / "home.json", ENGLISH)

    @staticmethod
    def _write_dictionary(path: Path, dictionary: dict[str, object]) -> None:
        path.write_text(
            json.dumps(dictionary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_all_locales_pass_with_external_source_and_identical_values(self) -> None:
        errors, report = validate_locales(self.root, self.source_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(report), len(EXPECTED_LOCALES) + 1)
        self.assertTrue(
            any("not a full human translation review" in line for line in report)
        )

    def test_placeholder_parser_handles_handlebars_icu_urls_and_quoted_braces(self) -> None:
        placeholders = extract_placeholders(
            "See https://example.test/{userId}?q={query}; "
            "{{displayName}}; "
            "{count, plural, =0 {none} one {# item for {name}} other {# items for {name}}}; "
            "literal '{notAPlaceholder}'."
        )

        self.assertEqual(
            placeholders,
            Counter(
                {
                    ("icu", "userId"): 1,
                    ("icu", "query"): 1,
                    ("double-curly", "displayName"): 1,
                    ("icu", "count"): 1,
                    ("icu", "name"): 2,
                }
            ),
        )

    def test_placeholder_name_and_occurrence_mismatch_is_rejected(self) -> None:
        translated = dict(ENGLISH)
        translated["url"] = "See https://example.test/users/{person}?q={query}"
        self._write_dictionary(self.root / "fr" / "home.json", translated)

        errors, _ = validate_locales(self.root, self.source_dir)

        self.assertTrue(any("fr/home.json:url: placeholder mismatch" in error for error in errors))

    def test_placeholder_occurrence_count_mismatch_is_rejected(self) -> None:
        translated = dict(ENGLISH)
        translated["url"] = "See https://example.test/users/{userId}/{userId}?q={query}"
        self._write_dictionary(self.root / "fr" / "home.json", translated)

        errors, _ = validate_locales(self.root, self.source_dir)

        self.assertTrue(any("fr/home.json:url: placeholder mismatch" in error for error in errors))

    def test_duplicate_json_key_is_rejected(self) -> None:
        (self.root / "fr" / "home.json").write_text(
            '{"plain":"Ready","plain":"Again"}', encoding="utf-8"
        )

        errors, _ = validate_locales(self.root, self.source_dir)

        self.assertTrue(any("duplicate JSON key 'plain'" in error for error in errors))

    def test_non_flat_or_empty_translation_is_rejected(self) -> None:
        self._write_dictionary(self.root / "de" / "home.json", {"plain": "  "})

        errors, _ = validate_locales(self.root, self.source_dir)

        self.assertTrue(any("must be a non-empty string" in error for error in errors))

        self._write_dictionary(self.root / "de" / "home.json", {"plain": {"nested": "no"}})
        errors, _ = validate_locales(self.root, self.source_dir)
        self.assertTrue(any("must be a string (flat dictionary)" in error for error in errors))

    def test_missing_and_unexpected_keys_and_namespaces_are_rejected(self) -> None:
        self._write_dictionary(self.root / "ar" / "home.json", {"plain": "Ready"})
        self._write_dictionary(self.root / "ca-ES" / "home.json", {**ENGLISH, "extra": "Unexpected"})
        (self.root / "cs" / "home.json").unlink()
        self._write_dictionary(self.root / "cs" / "extra.json", {"extra": "Unexpected"})

        errors, _ = validate_locales(self.root, self.source_dir)

        self.assertTrue(any("ar/home.json" in error and "missing keys" in error for error in errors))
        self.assertTrue(any("ca-ES/home.json" in error and "unexpected keys" in error for error in errors))
        self.assertTrue(any("cs: missing namespace files" in error for error in errors))
        self.assertTrue(any("cs: unexpected namespace files" in error for error in errors))

    def test_fixed_locale_set_rejects_missing_and_unexpected_directories(self) -> None:
        (self.root / "tr" / "home.json").unlink()
        (self.root / "tr").rmdir()
        (self.root / "xx").mkdir()

        errors, _ = validate_locales(self.root, self.source_dir)

        self.assertTrue(any("missing locale directories: tr" in error for error in errors))
        self.assertTrue(any("unexpected locale directories: xx" in error for error in errors))

    def test_english_locale_values_must_match_external_source(self) -> None:
        changed = dict(ENGLISH)
        changed["plain"] = "Prepared"
        self._write_dictionary(self.root / "en" / "home.json", changed)

        errors, _ = validate_locales(self.root, self.source_dir)

        self.assertTrue(any("English value differs from source" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
