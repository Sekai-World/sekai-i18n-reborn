#!/usr/bin/env python3
"""Validate locale dictionaries against the English source without dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_LOCALES = (
    "ar",
    "ca-ES",
    "cs",
    "de",
    "en",
    "es",
    "es-419",
    "es-MX",
    "fr",
    "he-IL",
    "id",
    "it",
    "ja",
    "ko",
    "ms",
    "nl",
    "pl",
    "pt-BR",
    "pt",
    "ro",
    "ru",
    "sk-SK",
    "th",
    "tr",
    "uk",
    "vi-VN",
    "yue",
    "zh-CN",
    "zh-TW",
)

_PLACEHOLDER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_ICU_TYPE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_SELECTION_TYPES = {"plural", "select", "selectordinal"}
PlaceholderCounter = Counter[tuple[str, str]]


class DictionaryError(ValueError):
    """A dictionary is not strict JSON or does not follow the flat-map format."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DictionaryError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise DictionaryError(f"non-standard JSON constant {value!r}")


def load_dictionary(path: Path) -> dict[str, str]:
    """Load a strict flat dictionary and reject duplicate keys at every depth."""
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DictionaryError) as error:
        raise DictionaryError(str(error)) from error

    if not isinstance(data, dict):
        raise DictionaryError("top-level JSON value must be an object")

    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise DictionaryError("dictionary keys must be non-empty strings")
        if not isinstance(value, str):
            raise DictionaryError(f"value for {key!r} must be a string (flat dictionary)")
        if not value.strip():
            raise DictionaryError(f"value for {key!r} must be a non-empty string")

    return data


def _skip_icu_quoted_text(text: str, position: int) -> int:
    """Skip an ICU apostrophe-quoted syntax span, or a literal apostrophe."""
    if position + 1 < len(text) and text[position + 1] == "'":
        return position + 2
    if position + 1 >= len(text) or text[position + 1] not in "{}":
        return position + 1

    cursor = position + 1
    while cursor < len(text):
        if text[cursor] == "'":
            if cursor + 1 < len(text) and text[cursor + 1] == "'":
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    return len(text)


def _find_matching_brace(text: str, opening: int) -> int | None:
    """Find an ICU argument's closing brace while respecting apostrophe quoting."""
    depth = 1
    cursor = opening + 1
    while cursor < len(text):
        character = text[cursor]
        if character == "'":
            cursor = _skip_icu_quoted_text(text, cursor)
        elif character == "{":
            depth += 1
            cursor += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return cursor
            cursor += 1
        else:
            cursor += 1
    return None


def _parse_selection_options(text: str, cursor: int) -> tuple[PlaceholderCounter, int] | None:
    """Parse plural/select branch bodies, excluding their selector braces."""
    nested: PlaceholderCounter = Counter()
    while cursor < len(text):
        while cursor < len(text) and (text[cursor].isspace() or text[cursor] == ","):
            cursor += 1
        if cursor >= len(text):
            return None
        if text[cursor] == "}":
            return nested, cursor

        if text.startswith("offset:", cursor):
            offset_match = re.match(r"offset:\s*-?\d+", text[cursor:])
            if offset_match is not None:
                cursor += offset_match.end()
                continue

        selector_end = cursor
        while selector_end < len(text) and not text[selector_end].isspace() and text[selector_end] not in "{}":
            selector_end += 1
        if selector_end == cursor:
            return None
        cursor = selector_end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            return None

        closing = _find_matching_brace(text, cursor)
        if closing is None:
            return None
        nested.update(extract_placeholders(text[cursor + 1 : closing]))
        cursor = closing + 1

    return None


def _parse_icu_argument(text: str, opening: int) -> tuple[PlaceholderCounter, int] | None:
    """Parse simple and selection-style ICU arguments beginning at ``opening``."""
    name_match = _PLACEHOLDER_NAME.match(text, opening + 1)
    if name_match is None:
        return None
    name = name_match.group(0)
    cursor = name_match.end()
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1

    if cursor < len(text) and text[cursor] == "}":
        return Counter({("icu", name): 1}), cursor + 1
    if cursor >= len(text) or text[cursor] != ",":
        return None

    type_start = cursor + 1
    while type_start < len(text) and text[type_start].isspace():
        type_start += 1
    type_match = _ICU_TYPE.match(text, type_start)
    if type_match is None:
        return None
    argument_type = type_match.group(0)
    cursor = type_match.end()

    if argument_type in _SELECTION_TYPES:
        if cursor >= len(text) or text[cursor] != ",":
            return None
        options = _parse_selection_options(text, cursor + 1)
        if options is None:
            return None
        nested, closing = options
        result: PlaceholderCounter = Counter({("icu", name): 1})
        result.update(nested)
        return result, closing + 1

    closing = _find_matching_brace(text, opening)
    if closing is None:
        return None
    return Counter({("icu", name): 1}), closing + 1


def extract_placeholders(text: str) -> PlaceholderCounter:
    """Return placeholder syntax/name counts for ICU, URL, and ``{{name}}`` tokens.

    Brace tokens in URL paths and queries use the same named-argument syntax as
    ICU simple arguments. ICU plural/select branch braces are parsed as message
    boundaries rather than mistaken for additional argument names.
    """
    result: PlaceholderCounter = Counter()
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "'":
            cursor = _skip_icu_quoted_text(text, cursor)
            continue

        if text.startswith("{{", cursor):
            closing = text.find("}}", cursor + 2)
            if closing >= 0:
                candidate = text[cursor + 2 : closing].strip()
                if _PLACEHOLDER_NAME.fullmatch(candidate):
                    result[("double-curly", candidate)] += 1
                cursor = closing + 2
                continue

        if text[cursor] == "{":
            parsed = _parse_icu_argument(text, cursor)
            if parsed is not None:
                placeholders, cursor = parsed
                result.update(placeholders)
                continue

        cursor += 1
    return result


def _describe_placeholders(placeholders: PlaceholderCounter) -> str:
    if not placeholders:
        return "none"
    return ", ".join(
        f"{syntax} {name} ×{count}"
        for (syntax, name), count in sorted(placeholders.items())
    )


def validate_locales(locale_root: Path, source_dir: Path) -> tuple[list[str], list[str]]:
    """Return validation errors and a per-locale coverage report."""
    errors: list[str] = []
    report: list[str] = []
    if not locale_root.is_dir():
        return [f"locale root does not exist: {locale_root}"], report
    if not source_dir.is_dir():
        return [f"English source directory does not exist: {source_dir}"], report

    source_paths = sorted(source_dir.glob("*.json"))
    if not source_paths:
        return [f"English source has no namespace JSON files: {source_dir}"], report

    source: dict[str, dict[str, str]] = {}
    for path in source_paths:
        try:
            source[path.name] = load_dictionary(path)
        except DictionaryError as error:
            errors.append(f"English source {path}: {error}")
    if errors:
        return errors, report

    expected_namespaces = set(source)
    expected_key_count = sum(len(dictionary) for dictionary in source.values())
    report.append(
        f"English source: {len(expected_namespaces)} namespaces, {expected_key_count} keys"
    )

    actual_locale_dirs = {
        path.name
        for path in locale_root.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name not in {"scripts", "tests"}
    }
    expected_locale_set = set(EXPECTED_LOCALES)
    missing_locales = sorted(expected_locale_set - actual_locale_dirs)
    unexpected_locales = sorted(actual_locale_dirs - expected_locale_set)
    if missing_locales:
        errors.append(f"missing locale directories: {', '.join(missing_locales)}")
    if unexpected_locales:
        errors.append(f"unexpected locale directories: {', '.join(unexpected_locales)}")

    for locale in EXPECTED_LOCALES:
        locale_dir = locale_root / locale
        if not locale_dir.is_dir():
            continue

        locale_paths = {path.name: path for path in locale_dir.glob("*.json")}
        locale_namespaces = set(locale_paths)
        missing_namespaces = sorted(expected_namespaces - locale_namespaces)
        unexpected_namespaces = sorted(locale_namespaces - expected_namespaces)
        if missing_namespaces:
            errors.append(
                f"{locale}: missing namespace files: {', '.join(missing_namespaces)}"
            )
        if unexpected_namespaces:
            errors.append(
                f"{locale}: unexpected namespace files: {', '.join(unexpected_namespaces)}"
            )

        loaded: dict[str, dict[str, str]] = {}
        for namespace, path in locale_paths.items():
            try:
                loaded[namespace] = load_dictionary(path)
            except DictionaryError as error:
                errors.append(f"{locale}/{namespace}: {error}")

        present_keys = 0
        same_as_english = 0
        for namespace, english_dictionary in source.items():
            dictionary = loaded.get(namespace)
            if dictionary is None:
                continue
            present_keys += len(dictionary)
            english_keys = set(english_dictionary)
            locale_keys = set(dictionary)
            missing_keys = sorted(english_keys - locale_keys)
            unexpected_keys = sorted(locale_keys - english_keys)
            if missing_keys or unexpected_keys:
                details = []
                if missing_keys:
                    details.append(f"missing keys: {', '.join(missing_keys)}")
                if unexpected_keys:
                    details.append(f"unexpected keys: {', '.join(unexpected_keys)}")
                errors.append(f"{locale}/{namespace}: " + "; ".join(details))

            for key in sorted(english_keys & locale_keys):
                english_value = english_dictionary[key]
                translated_value = dictionary[key]
                if translated_value == english_value:
                    same_as_english += 1
                if locale == "en" and translated_value != english_value:
                    errors.append(
                        f"en/{namespace}: English value differs from source for {key!r}"
                    )

                expected_placeholders = extract_placeholders(english_value)
                actual_placeholders = extract_placeholders(translated_value)
                if expected_placeholders != actual_placeholders:
                    errors.append(
                        f"{locale}/{namespace}:{key}: placeholder mismatch "
                        f"(expected {_describe_placeholders(expected_placeholders)}; "
                        f"found {_describe_placeholders(actual_placeholders)})"
                    )

        report.append(
            f"{locale}: {len(locale_namespaces & expected_namespaces)}/"
            f"{len(expected_namespaces)} namespaces, {present_keys}/"
            f"{expected_key_count} keys; {same_as_english} values match English "
            "(informational only; not a full human translation review)"
        )

    return errors, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Example: python3 scripts/validate_dictionaries.py --source-dir "
            "<viewer-worktree>/packages/i18n-source/content-site. "
            "Identical-to-English counts are informational and do not constitute "
            "a complete human translation review."
        ),
    )
    parser.add_argument(
        "--locale-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="directory containing the fixed locale folders (default: repository root)",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="English namespace directory (default: <locale-root>/en)",
    )
    args = parser.parse_args(argv)
    source_dir = args.source_dir or args.locale_root / "en"

    errors, report = validate_locales(args.locale_root, source_dir)
    for line in report:
        print(line)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Validated all {len(EXPECTED_LOCALES)} locales successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
