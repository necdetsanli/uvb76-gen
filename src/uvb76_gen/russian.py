"""uvb76_gen.russian.

Russian TTS-friendly formatting helpers for UVB-76 style output.

This module provides utilities to turn "UVB-76-ish" content into text that a
Russian TTS engine can read more consistently:

- Digit groups ("34179") can be expanded into Russian digit words
  ("ТРИ. ЧЕТЫРЕ. ОДИН. СЕМЬ. ДЕВЯТЬ.") to prevent fast/incorrect numeric reading.
- Callsigns can be "spelled out" as pronounceable Russian tokens for each letter
  and digit, so mixed Cyrillic/Latin callsigns like "УВБ76" become readable.
- Raw groups can be parsed from either:
  - digits ("34179 55014 ..."), or
  - Russian digit-word renderings ("ТРИ. ЧЕТЫРЕ. ...").

It also includes a simple A–Z -> Russian codeword mapping (e.g., NATO-style but
Russian), allowing you to derive a "names line" from a Vigenère key.

Design notes
------------
- This is not a linguistic perfection library; it is a pragmatic set of mappings
  intended to improve TTS robustness and consistency.
- Tokenization for Russian digit-word parsing is tolerant of punctuation and
  common separators (periods, commas, newlines).

"""

from __future__ import annotations

import re
from typing import Final

RUS_DIGIT_WORD: Final[dict[str, str]] = {
    "0": "НОЛЬ",
    "1": "ОДИН",
    "2": "ДВА",
    "3": "ТРИ",
    "4": "ЧЕТЫРЕ",
    "5": "ПЯТЬ",
    "6": "ШЕСТЬ",
    "7": "СЕМЬ",
    "8": "ВОСЕМЬ",
    "9": "ДЕВЯТЬ",
}

RUS_WORD_DIGIT: Final[dict[str, str]] = {v: k for k, v in RUS_DIGIT_WORD.items()}

# Russian names (pronunciations) for Latin letters A-Z, in Cyrillic.
# This is primarily used to spell callsigns/keys in a Russian TTS-friendly way.
LATIN_LETTER_RU_NAME: Final[dict[str, str]] = {
    "A": "А",
    "B": "БЭ",
    "C": "СЭ",
    "D": "ДЭ",
    "E": "Е",
    "F": "ЭФ",
    "G": "ДЖИ",
    "H": "ЭЙЧ",
    "I": "И",
    "J": "ДЖЕЙ",
    "K": "КЭЙ",
    "L": "ЭЛ",
    "M": "ЭМ",
    "N": "ЭН",
    "O": "О",
    "P": "ПИ",
    "Q": "КЬЮ",
    "R": "ЭР",
    "S": "ЭС",
    "T": "ТЭ",
    "U": "У",
    "V": "ВЭ",
    "W": "ДАБЛЬЮ",
    "X": "ИКС",
    "Y": "ИГРЕК",
    "Z": "ЗЭД",
}

# Minimal Cyrillic letter names needed for common callsigns like "УВБ".
CYRILLIC_LETTER_RU_NAME: Final[dict[str, str]] = {
    "А": "А",
    "Б": "БЭ",
    "В": "ВЭ",
    "Г": "ГЭ",
    "Д": "ДЭ",
    "Е": "Е",
    "Ж": "ЖЭ",
    "З": "ЗЭ",
    "И": "И",
    "Й": "И КРАТКОЕ",
    "К": "КА",
    "Л": "ЭЛ",
    "М": "ЭМ",
    "Н": "ЭН",
    "О": "О",
    "П": "ПЭ",
    "Р": "ЭР",
    "С": "ЭС",
    "Т": "ТЭ",
    "У": "У",
    "Ф": "ЭФ",
    "Х": "ХА",
    "Ц": "ЦЭ",
    "Ч": "ЧЭ",
    "Ш": "ША",
    "Щ": "ЩА",
    "Ы": "Ы",
    "Э": "Э",
    "Ю": "Ю",
    "Я": "Я",
}

RU_CODEWORDS: dict[str, str] = {
    "A": "АННА",
    "B": "БОРИС",
    "C": "ЦЕНТР",
    "D": "ДМИТРИЙ",
    "E": "ЕЛЕНА",
    "F": "ФЁДОР",
    "G": "ГРИГОРИЙ",
    "H": "ХАРИТОН",
    "I": "ИРИНА",
    "J": "ЮЛИЯ",
    "K": "КОНСТАНТИН",
    "L": "ЛЕОНИД",
    "M": "МИХАИЛ",
    "N": "НИКОЛАЙ",
    "O": "ОЛЕГ",
    "P": "ПАВЕЛ",
    "Q": "КВАЗАР",
    "R": "РОМАН",
    "S": "СЕРГЕЙ",
    "T": "ТАТЬЯНА",
    "U": "УЛЬЯНА",
    "V": "ВИКТОР",
    "W": "ВАЛЕРИЙ",
    "X": "КСЕНИЯ",
    "Y": "ЯКОВ",
    "Z": "ЗИНАИДА",
}

_TOKEN_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"[^\w]+", re.UNICODE)


def spell_callsign_ru(callsign: str) -> str:
    """Spell a callsign as Russian-friendly tokens (letters + digit words).

    Each character in the callsign is mapped to a pronounceable Russian token:

    - ASCII digits -> Russian digit words (e.g., "7" -> "СЕМЬ")
    - Latin letters A–Z -> Russian letter names in Cyrillic (e.g., "B" -> "БЭ")
    - Cyrillic letters -> Russian letter names (subset defined in CYRILLIC_LETTER_RU_NAME)
    - Separators/punctuation are ignored

    The result is a period-separated sequence ending with a trailing period,
    which tends to make many TTS engines pause slightly between tokens.

    Args:
        callsign:
            Callsign string, e.g., "УВБ76" or "UVB76".

    Returns:
        A Russian TTS-friendly spelled representation, or an empty string if
        nothing could be tokenized.

    """
    tokens: list[str] = []
    for ch in callsign.strip():
        if ch.isdigit():
            tokens.append(RUS_DIGIT_WORD[ch])
            continue

        up = ch.upper()
        if up in LATIN_LETTER_RU_NAME:
            tokens.append(LATIN_LETTER_RU_NAME[up])
            continue

        if up in CYRILLIC_LETTER_RU_NAME:
            tokens.append(CYRILLIC_LETTER_RU_NAME[up])
            continue

        # Ignore separators like '-', '_', spaces, etc.
    if not tokens:
        return ""
    return ". ".join(tokens) + "."


def format_group_ru(group: str) -> str:
    """Render a 5-digit group as Russian digit words.

    Example:
        "34179" -> "ТРИ. ЧЕТЫРЕ. ОДИН. СЕМЬ. ДЕВЯТЬ."

    Notes:
    - Non-digit characters inside the input are ignored.
    - The function assumes the group is intended to represent exactly 5 digits;
      callers typically pass the 5-digit cipher groups produced elsewhere.

    Args:
        group:
            A group string that should contain digits, typically length 5.

    Returns:
        A period-separated Russian digit-word sequence with a trailing period.

    """
    digits = [ch for ch in group.strip() if ch.isdigit()]
    tokens = [RUS_DIGIT_WORD[d] for d in digits]
    return ". ".join(tokens) + "."


def format_groups_ru(groups: list[str], per_line: int) -> str:
    """Format groups into Russian digit words and wrap them into lines.

    Each 5-digit group is converted via `format_group_ru` and groups are wrapped
    so that each output line contains `per_line` groups.

    Args:
        groups:
            List of group strings, typically produced by the cipher encoder.
        per_line:
            Number of groups per output line. Must be >= 1.

    Returns:
        A newline-terminated string containing wrapped lines of rendered groups.

    Raises:
        ValueError:
            If per_line is <= 0.

    """
    if per_line <= 0:
        raise ValueError("per_line must be >= 1")

    lines: list[str] = []
    for i in range(0, len(groups), per_line):
        chunk = groups[i : i + per_line]
        rendered = " ".join(format_group_ru(g) for g in chunk)
        lines.append(rendered)
    return "\n".join(lines) + "\n"


def parse_groups_maybe_ru(text: str) -> list[str]:
    """Parse 5-digit groups from either raw digits or Russian digit-word text.

    This function supports two input styles:

    1) Raw digits:
        "34179 55014 81937"
        Any digits found are collected and chunked into 5-digit groups.

    2) Russian digit words:
        "ТРИ. ЧЕТЫРЕ. ОДИН. СЕМЬ. ДЕВЯТЬ. ..."
        Tokens are split on punctuation/whitespace and matched against known
        Russian digit words. Digits are accumulated and chunked into groups.

    The function chooses a "fast path" if the input contains many digits.

    Args:
        text:
            Input text containing either raw digits or Russian digit words.

    Returns:
        A list of 5-digit group strings.

    Raises:
        ValueError:
            If trailing digits/words do not form complete 5-digit groups,
            or if no groups can be parsed.

    """
    # First, fast-path: if it contains many digits, rely on raw digit extraction.
    raw_digits = re.findall(r"\d", text)
    if len(raw_digits) >= 5:
        groups: list[str] = []
        buf: list[str] = []
        for d in raw_digits:
            buf.append(d)
            if len(buf) == 5:
                groups.append("".join(buf))
                buf.clear()
        if buf:
            raise ValueError("Trailing digits not forming a complete 5-digit group.")
        return groups

    # Otherwise, try Russian word tokens.
    tokens = [t for t in _TOKEN_SPLIT_RE.split(text.upper()) if t]
    digits_buf: list[str] = []
    groups_out: list[str] = []

    for t in tokens:
        if t in RUS_WORD_DIGIT:
            digits_buf.append(RUS_WORD_DIGIT[t])

        # Flush every 5 digits into a group.
        while len(digits_buf) >= 5:
            groups_out.append("".join(digits_buf[:5]))
            digits_buf = digits_buf[5:]

    if digits_buf:
        raise ValueError("Trailing Russian digit words not forming a complete 5-digit group.")

    if not groups_out:
        raise ValueError("No groups could be parsed from input.")

    return groups_out


def codewords_from_key(key: str) -> list[str]:
    """Derive Russian codewords from an A–Z key, preserving order and repeats.

    The UVB-76-style "names line" is often rendered as a sequence of Russian
    codewords. This helper maps each Latin A–Z character in the provided key
    to a Russian codeword using RU_CODEWORDS.

    Behavior:
    - Non A–Z characters are ignored.
    - Repeated letters are kept (the output length corresponds to the number of
      A–Z letters present in the key).
    - Unknown mappings are skipped (though RU_CODEWORDS is defined for A–Z).

    Args:
        key:
            Key string (expected to be sanitized elsewhere, but this function
            is tolerant of whitespace and non-letter characters).

    Returns:
        A list of Russian codewords corresponding to each letter in the key.

    """
    out: list[str] = []

    for ch in key.strip().upper():
        if "A" <= ch <= "Z":
            w = RU_CODEWORDS.get(ch)
            if w is not None:
                out.append(w)

    return out
