"""uvb76_gen.crypto.

Cipher and number-group encoding utilities.

This module implements the core "UVB-ish" transformation pipeline used by the project:

1) **Sanitize inputs**
   - Plaintext is reduced to uppercase A–Z only.
   - Keys are reduced to uppercase A–Z only (and must not be empty).

2) **Encrypt (toy / stylistic)**
   - A classic Vigenère-style cipher over the 0..25 alphabet is applied to the plaintext.

3) **Pack into 5-digit groups**
   - Cipher symbols are padded to a multiple of 3 using a sentinel value (26).
   - Triplets are packed in base-27 into a number N in [0..19682].
   - A deterministic per-triplet offset derived from `mask_key` is added, producing a
     5-digit group in [00000..99999] (bounded by construction).

4) **Decode**
   - The process is reversible if (and only if) the same `mask_key` is used to remove
     offsets, then the same `key` is used for Vigenère decryption.

Important notes
- This is **not cryptographically secure** and is meant for stylistic, reproducible
  "number station"-like encoding.
- `key` affects the A–Z encryption layer (Vigenère).
- `mask_key` affects only the numeric group masking (offsets).
- Sanitization strips non A–Z characters. For example, "NECDET" stays "NECDET", but
  if some character is not in A–Z it will be removed entirely.

Public API
- `encrypt_to_groups`: plaintext -> list of 5-digit strings
- `decrypt_from_groups`: list of 5-digit strings -> plaintext
- Helpers for parsing and for the underlying steps are also exposed.

"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass

from .errors import Uvb76GenError

_AZ_RE = re.compile(r"[^A-Z]")


@dataclass(frozen=True)
class CipherConfig:
    """Configuration for the UVB-ish encoding pipeline.

    Attributes:
        key:
            Vigenère key used for the A–Z encryption layer. It is sanitized to A–Z
            and must not be empty after sanitization.
        mask_key:
            Secondary key used only to derive deterministic numeric offsets for each
            packed triplet. This makes groups look less directly related to the raw
            packed values while remaining reversible.

    """

    key: str
    mask_key: str


def sanitize_plaintext(text: str) -> str:
    """Normalize plaintext into the supported alphabet.

    The cipher layer operates on the 26-letter Latin alphabet only.
    Any character outside A–Z is removed.

    Args:
        text: Arbitrary input text.

    Returns:
        Uppercased string containing only A–Z characters.

    """
    return _AZ_RE.sub("", text.upper())


def sanitize_key(key: str) -> str:
    """Normalize a key into the supported alphabet and validate it.

    Keys are reduced to uppercase A–Z and must remain non-empty afterwards.

    Args:
        key: User-provided key.

    Returns:
        Uppercased A–Z-only key.

    Raises:
        Uvb76GenError: If the key contains no A–Z letters after sanitization.

    """
    k = _AZ_RE.sub("", key.upper())
    if len(k) == 0:
        raise Uvb76GenError("Key must contain at least one A-Z letter.")
    return k


def letters_to_nums(text_az: str) -> list[int]:
    """Convert A–Z characters into numeric symbols (0..25).

    Args:
        text_az: String containing only A–Z.

    Returns:
        List of integers where A->0, B->1, ..., Z->25.

    """
    return [ord(ch) - 65 for ch in text_az]


def nums_to_letters(nums: list[int]) -> str:
    """Convert numeric symbols (0..25) back into A–Z characters.

    Args:
        nums: List of integers in [0..25].

    Returns:
        String containing A–Z characters.

    """
    return "".join(chr(65 + n) for n in nums)


def vigenere_encrypt(plain: list[int], key: list[int]) -> list[int]:
    """Encrypt using a Vigenère-style cipher over the 0..25 alphabet.

    Each plaintext symbol is shifted by the corresponding key symbol (cycled).

    Args:
        plain: Plaintext symbols in [0..25].
        key: Key symbols in [0..25]. Must be non-empty.

    Returns:
        Ciphertext symbols in [0..25].

    """
    out: list[int] = []
    for i, p in enumerate(plain):
        k = key[i % len(key)]
        out.append((p + k) % 26)
    return out


def vigenere_decrypt(cipher: list[int], key: list[int]) -> list[int]:
    """Decrypt a Vigenère-style cipher over the 0..25 alphabet.

    This reverses `vigenere_encrypt` when the same key is used.

    Args:
        cipher: Ciphertext symbols in [0..25].
        key: Key symbols in [0..25]. Must be non-empty.

    Returns:
        Plaintext symbols in [0..25].

    """
    out: list[int] = []
    for i, c in enumerate(cipher):
        k = key[i % len(key)]
        out.append((c - k + 26) % 26)
    return out


def _seed32(s: str) -> int:
    """Derive a deterministic 32-bit seed from an arbitrary string.

    We hash the string with SHA-256 and take the first 4 bytes as an unsigned
    big-endian integer.

    Args:
        s: Input string.

    Returns:
        32-bit unsigned integer seed.

    """
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], byteorder="big", signed=False)


def xorshift32(seed: int) -> Iterator[int]:
    """Generate an infinite deterministic PRNG stream (xorshift32).

    This PRNG is used only for deterministic offset generation.
    It is fast and repeatable but **not** cryptographically secure.

    Args:
        seed: Initial seed value (treated as uint32).

    Yields:
        Unsigned 32-bit integers indefinitely.

    """
    x = seed & 0xFFFFFFFF
    while True:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= (x >> 17) & 0xFFFFFFFF
        x ^= (x << 5) & 0xFFFFFFFF
        yield x & 0xFFFFFFFF


def encode_groups(cipher_nums: list[int], mask_key: str) -> list[str]:
    """Encode ciphertext symbols (0..25) into 5-digit groups.

    Encoding rationale
    - UVB-ish broadcasts often present messages as fixed-width numeric groups.
    - We pack symbols to reduce length and add a deterministic offset so the groups
      don't look like a simple base conversion.

    Steps
    1) **Pad** ciphertext to a multiple of 3 with a sentinel value `26`.
       - 26 is outside the real alphabet [0..25], so it can be safely removed later.
    2) **Pack triplets** (a, b, c) as base-27:
         N = a*27^2 + b*27 + c
       where N is in [0..19682].
    3) **Offset** each N by a deterministic pseudo-random value:
         off = PRNG(mask_key)[i] % 80318
         group = N + off
       We choose 80318 so that N+off stays below 100000.

    Args:
        cipher_nums: Cipher symbols in [0..25].
        mask_key: A–Z-only key that seeds the PRNG stream.

    Returns:
        List of zero-padded 5-digit strings.

    """
    pad = 26
    nums: list[int] = list(cipher_nums)
    while (len(nums) % 3) != 0:
        nums.append(pad)

    prng = xorshift32(_seed32(mask_key))
    groups: list[str] = []

    for i in range(0, len(nums), 3):
        a = nums[i]
        b = nums[i + 1]
        c = nums[i + 2]
        n = a * 27 * 27 + b * 27 + c

        off = next(prng) % 80318
        g = n + int(off)
        groups.append(str(g).zfill(5))

    return groups


def decode_groups(groups: list[str], mask_key: str) -> list[int]:
    """Decode 5-digit groups back into ciphertext symbols (0..25).

    This reverses `encode_groups` when the same `mask_key` is used.

    Steps
    1) Parse each group as an integer.
    2) Subtract the deterministic offset for that group index.
    3) Unpack base-27 triplets back into symbol values.
    4) Remove trailing padding sentinel values (26).
    5) Validate that all remaining values are in [0..25].

    Args:
        groups: List of 5-digit group strings.
        mask_key: A–Z-only key used to reproduce the PRNG offsets.

    Returns:
        Ciphertext symbol list in [0..25].

    Raises:
        Uvb76GenError: If group parsing fails or unpacked values are out of range.

    """
    prng = xorshift32(_seed32(mask_key))
    out: list[int] = []

    for g in groups:
        if g.strip() == "":
            continue
        try:
            gi = int(g, 10)
        except ValueError as exc:
            raise Uvb76GenError(f"Invalid group: {g}") from exc

        off = next(prng) % 80318
        n = gi - int(off)
        if n < 0 or n > 19682:
            raise Uvb76GenError(f"Decoded triplet out of range for group={g}")

        a = n // (27 * 27)
        b = (n // 27) % 27
        c = n % 27

        out.extend([a, b, c])

    # Remove padding sentinel(s) added by encode_groups.
    while len(out) > 0 and out[-1] == 26:
        out.pop()

    for v in out:
        if v < 0 or v > 25:
            raise Uvb76GenError("Decoded symbols include out-of-range values.")
    return out


def parse_groups_text(text: str) -> list[str]:
    """Parse whitespace-separated digit groups from text.

    Args:
        text: A string containing groups separated by spaces/newlines.

    Returns:
        A list of non-empty tokens (raw group strings).

    """
    parts = re.split(r"\s+", text.strip())
    return [p for p in parts if p != ""]


def encrypt_to_groups(plaintext: str, cfg: CipherConfig) -> list[str]:
    """High-level helper: plaintext -> 5-digit groups.

    Args:
        plaintext: Input message. Only A–Z characters are retained.
        cfg: Cipher configuration containing `key` and `mask_key`.

    Returns:
        List of 5-digit group strings.

    Raises:
        Uvb76GenError: If key/mask_key are empty after sanitization.

    """
    clean = sanitize_plaintext(plaintext)
    k = sanitize_key(cfg.key)
    mk = sanitize_key(cfg.mask_key)

    p = letters_to_nums(clean)
    key_nums = letters_to_nums(k)
    c = vigenere_encrypt(p, key_nums)
    return encode_groups(c, mk)


def decrypt_from_groups(groups: list[str], cfg: CipherConfig) -> str:
    """High-level helper: 5-digit groups -> plaintext.

    Args:
        groups: List of 5-digit group strings (as produced by `encrypt_to_groups`).
        cfg: Cipher configuration containing `key` and `mask_key`.

    Returns:
        Decrypted plaintext (A–Z only).

    Raises:
        Uvb76GenError: If decoding fails or keys are invalid.

    """
    k = sanitize_key(cfg.key)
    mk = sanitize_key(cfg.mask_key)

    cipher_nums = decode_groups(groups, mk)
    key_nums = letters_to_nums(k)
    plain_nums = vigenere_decrypt(cipher_nums, key_nums)
    return nums_to_letters(plain_nums)
