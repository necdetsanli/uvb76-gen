"""uvb76_gen.broadcast.

Broadcast script generation utilities.

This module turns generated 5-digit groups into a human-/TTS-friendly broadcast script.

There are two output styles:

- `make_script`:
  Produces a simple "raw" script (ASCII/Latin) that keeps digit groups as-is.
  Useful for debugging or for non-Russian voices.

- `make_script_ru`:
  Produces a Russian TTS-friendly script:
  - Callsign is "spelled" in Cyrillic-friendly form via `spell_callsign_ru`.
  - Digit groups are rendered as Russian digit words via `format_groups_ru`.
  - Ends with an explicit terminator line ("КОНЕЦ.") so it is obvious when the
    message has finished.

The caller controls formatting and repetition through `BroadcastConfig`.

Notes:
- This module does not generate groups. It only formats them.
- The Russian helpers live in `uvb76_gen.russian`.

"""

from __future__ import annotations

from dataclasses import dataclass

from .russian import format_groups_ru, spell_callsign_ru


@dataclass(frozen=True)
class BroadcastConfig:
    """Configuration for broadcast script rendering.

    Attributes:
        callsign:
            The station callsign as provided by the user (e.g., "УВБ76").
            The script will normalize it to uppercase for display.
        names:
            List of name/codeword tokens to be printed on the header line.
            Empty/whitespace-only entries should be filtered out by the caller.
        groups_per_line:
            Number of 5-digit groups to print per line.
        repeat:
            If True, the group body is appended one more time at the end
            (a common number-station-like convention).

    """

    callsign: str
    names: list[str]
    groups_per_line: int = 7
    repeat: bool = True


def format_groups(groups: list[str], per_line: int) -> str:
    """Format raw digit groups into wrapped lines.

    This formatter expects that `groups` already contains only digit-group tokens
    (e.g., "34179", "55014", ...). No validation is performed here.

    Args:
        groups:
            List of digit-group strings.
        per_line:
            Maximum number of groups per output line.

    Returns:
        A newline-terminated string with groups wrapped at `per_line`.

    """
    lines: list[str] = []
    for i in range(0, len(groups), per_line):
        lines.append(" ".join(groups[i : i + per_line]))
    return "\n".join(lines) + "\n"


def make_script(cfg: BroadcastConfig, groups: list[str]) -> str:
    """Build an ASCII/raw broadcast script (digits + Latin letters).

    Output shape (example):

        UVB76
        ROMAN. ANNA. DMITRY.

        34179 55014 81937
        ...

        34179 55014 81937
        ...

    Notes:
    - Callsign and names are uppercased.
    - The body is the wrapped output of `format_groups`.
    - If `cfg.repeat` is True, the body is repeated once at the end.

    Args:
        cfg:
            Broadcast configuration.
        groups:
            List of digit-group strings.

    Returns:
        Fully formatted script (newline-terminated).

    """
    callsign = cfg.callsign.strip().upper()
    names_line = ". ".join([n.strip().upper() for n in cfg.names if n.strip() != ""])

    body = format_groups(groups, cfg.groups_per_line).strip()
    script = f"{callsign}\n{names_line}.\n\n{body}\n"

    if cfg.repeat:
        script += f"\n{body}\n"

    return script


def make_script_ru(cfg: BroadcastConfig, groups: list[str]) -> str:
    """Build a Russian TTS-friendly broadcast script (Cyrillic + digit words).

    Output shape (example):

        У. В. Б. 7. 6.
        У. В. Б. 7. 6.
        РОМАН. АННА. ДМИТРИЙ.

        3, 4, 1, 7, 9.
        5, 5, 0, 1, 4.

        КОНЕЦ.

    Notes:
    - The callsign line is produced by `spell_callsign_ru` and duplicated for
      a more "authentic" feel.
    - Names are uppercased Cyrillic tokens separated by ". ".
    - Group body uses `format_groups_ru` (Russian digit words / punctuation).
    - "КОНЕЦ." is appended to make the end explicit for listeners and TTS.

    Args:
        cfg:
            Broadcast configuration.
        groups:
            List of 5-digit group strings.

    Returns:
        Fully formatted Russian script (newline-terminated).

    """
    callsign_line = spell_callsign_ru(cfg.callsign)
    names_line = ". ".join([n.strip().upper() for n in cfg.names if n.strip() != ""])
    if names_line:
        names_line += "."

    body = format_groups_ru(groups, cfg.groups_per_line).strip()
    end_line = "КОНЕЦ."  # Russian "END."

    # Keep a blank line before the body, and before the end marker.
    parts = [callsign_line, callsign_line]
    if names_line:
        parts.append(names_line)
    parts.extend(["", body, "", end_line])

    script = "\n".join(parts).rstrip() + "\n"

    if cfg.repeat:
        script += "\n" + body + "\n\n" + end_line + "\n"

    return script
