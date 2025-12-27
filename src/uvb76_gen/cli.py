"""uvb76_gen.cli.

Command-line interface for **uvb76-gen**.

This module exposes a small Typer-based CLI that can:

- Generate UVB-76-style digit groups using a Vigenère-like cipher and a deterministic masking PRNG.
- Render a Russian TTS-friendly broadcast script (Cyrillic callsign, codewords, Russian digit words).
- Decode previously generated groups back into plaintext.
- Produce a UVB-ish audio mix (static bed + buzzer windows + processed voice) via FFmpeg.

Design notes
- Validation errors are raised as :class:`~uvb76_gen.errors.Uvb76GenError` and converted to non-zero exit codes.
- Options are defined as module-level constants to keep defaults static and formatter/linter-friendly.
- The `--key` option is mandatory and is also used to derive Russian codewords when `--name` is not provided.
- Audio duration rules (minimum required length, padding, etc.) are enforced in the audio renderer.

Commands
- `gen`: Create `groups_raw.txt`, `groups.txt` (Russian digit words), and `broadcast.txt` (Russian script).
- `decode`: Accept raw digit groups or Russian digit words and recover plaintext.
- `render-audio`: Render a UVB-ish mix from a provided voice file.

Files written by `gen`
- `out/groups_raw.txt`: raw 5-digit groups (digits only).
- `out/groups.txt`: Russian digit words formatted for speech/TTS.
- `out/broadcast.txt`: Russian broadcast script including callsign and codewords.

"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .audio import (
    AudioRenderConfig,
    render_background_buzzer,
    render_static_voice,
    render_uvb_mix,
)
from .broadcast import BroadcastConfig, make_script_ru
from .crypto import CipherConfig, decrypt_from_groups, encrypt_to_groups, parse_groups_text
from .errors import Uvb76GenError
from .russian import codewords_from_key, format_groups_ru, parse_groups_maybe_ru

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

DEFAULT_CALLSIGN = "УВБ76"
DEFAULT_OUT_DIR = Path("out")
DEFAULT_GROUPS_PER_LINE = 7

DEFAULT_AUDIO_OUT = Path("out/mix.wav")


# Typer Option infos (avoid function-calls in defaults; keep Ruff happy)
TEXT_OPT = typer.Option(..., "--text", help="Plaintext message.")
KEY_OPT = typer.Option(..., "--key", help="Vigenere key (A-Z).")
MASK_KEY_OPT = typer.Option(None, "--mask-key", help="Mask key for offsets (default: key).")
CALLSIGN_OPT = typer.Option(
    DEFAULT_CALLSIGN, "--callsign", help="Callsign printed in broadcast script."
)
NAME_OPT = typer.Option(
    None,
    "--name",
    help="Name tokens (repeat option). Example: --name РОМАН --name АННА",
    show_default=False,
)
OUT_DIR_OPT = typer.Option(DEFAULT_OUT_DIR, "--out-dir", help="Output directory.")
GROUPS_PER_LINE_OPT = typer.Option(
    DEFAULT_GROUPS_PER_LINE, "--groups-per-line", help="Groups per output line."
)
NO_REPEAT_OPT = typer.Option(False, "--no-repeat", help="Do not repeat groups in script.")
VOICE_WAV_OPT = typer.Option(None, "--voice-wav", help="Optional voice audio file to render mix.")
AUDIO_OUT_OPT = typer.Option(None, "--audio-out", help="Audio output path (wav/mp3).")


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 text to disk, ensuring parent directories exist.

    Args:
        path: Target file path.
        content: Text content to write.

    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


@app.command("gen")
def gen(
    text: str = TEXT_OPT,
    key: str = KEY_OPT,
    mask_key: str | None = MASK_KEY_OPT,
    callsign: str = CALLSIGN_OPT,
    names: list[str] | None = NAME_OPT,
    out_dir: Path = OUT_DIR_OPT,
    groups_per_line: int = GROUPS_PER_LINE_OPT,
    no_repeat: bool = NO_REPEAT_OPT,
    voice_wav: Path | None = VOICE_WAV_OPT,
    audio_out: Path | None = AUDIO_OUT_OPT,
) -> None:
    """Generate digit groups + Russian broadcast script (and optional audio mix).

    This command:
    1) Encrypts plaintext into 5-digit groups.
    2) Produces Russian TTS-friendly output:
       - `groups.txt` (digit words)
       - `broadcast.txt` (callsign + codewords + groups)
    3) Also writes `groups_raw.txt` (digits) for debugging/decoding.

    Codewords:
    - If `--name` is provided, those tokens are used (empty items are ignored).
    - Otherwise, codewords are derived from `--key` via `codewords_from_key`.

    Audio:
    - If both `--voice-wav` and `--audio-out` are provided, an additional mixed
      UVB-ish audio file is rendered via FFmpeg.

    Raises:
        typer.Exit: Exit code 1 on domain errors, after printing a message.

    """
    try:
        mk = mask_key if mask_key is not None else key
        cfg = CipherConfig(key=key, mask_key=mk)
        groups = encrypt_to_groups(text, cfg)

        if names is not None and len(names) > 0:
            effective_names = [n for n in names if n.strip() != ""]
        else:
            effective_names = codewords_from_key(key)
            if len(effective_names) == 0:
                raise Uvb76GenError("Failed to derive Russian codewords from --key.")

        bcfg = BroadcastConfig(
            callsign=callsign,
            names=effective_names,
            groups_per_line=int(groups_per_line),
            repeat=not no_repeat,
        )

        # Files
        groups_path = out_dir / "groups.txt"  # Russian (digit words)
        groups_raw_path = out_dir / "groups_raw.txt"  # Raw digits (for decode/debug)
        script_path = out_dir / "broadcast.txt"  # Russian script

        _write_text(groups_raw_path, " ".join(groups) + "\n")
        _write_text(groups_path, format_groups_ru(groups, per_line=int(groups_per_line)))
        _write_text(script_path, make_script_ru(bcfg, groups))

        console.print(
            Panel.fit(
                f"Wrote:\n- {groups_path}\n- {groups_raw_path}\n- {script_path}",
                title="gen",
            )
        )

        if voice_wav is not None and audio_out is not None:
            render_uvb_mix(
                voice_wav=voice_wav,
                out_path=audio_out,
                cfg=AudioRenderConfig(duration_seconds=None),
            )
            console.print(Panel.fit(f"Wrote:\n- {audio_out}", title="audio"))

    except Uvb76GenError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("decode")
def decode(
    key: str = typer.Option(..., "--key", help="Vigenere key (A-Z)."),
    mask_key: str | None = typer.Option(None, "--mask-key", help="Mask key (default: key)."),
    groups_file: Path | None = typer.Option(
        None, "--groups-file", help="Path to groups.txt or groups_raw.txt."
    ),
    groups_text: str | None = typer.Option(
        None, "--groups", help="Groups as raw digits or Russian digit words."
    ),
) -> None:
    """Decode groups back to plaintext (raw digits or Russian digit words).

    Input sources:
    - `--groups-file`: Reads from a file (either raw digit groups or Russian digit words).
    - `--groups`: Accepts groups directly as a string.

    Parsing strategy:
    - First tries the basic whitespace group parser (digits).
    - If that fails, falls back to the Russian digit-word parser.

    Raises:
        typer.Exit: Exit code 2 if no input is provided, 1 on domain errors.

    """
    if (groups_file is None) and (groups_text is None):
        console.print("[bold red]Error:[/bold red] Provide --groups-file or --groups")
        raise typer.Exit(code=2)

    try:
        mk = mask_key if mask_key is not None else key
        cfg = CipherConfig(key=key, mask_key=mk)

        if groups_file is not None:
            raw = groups_file.read_text(encoding="utf-8")
        else:
            raw = groups_text if groups_text is not None else ""

        # Try the existing parser first (raw digit format), then fall back to Russian parser.
        try:
            groups = parse_groups_text(raw)
        except Exception:
            groups = parse_groups_maybe_ru(raw)

        plain = decrypt_from_groups(groups, cfg)
        console.print(Panel.fit(plain, title="decoded plaintext"))

    except Uvb76GenError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("render-audio")
def render_audio(
    voice_wav: Path = typer.Option(..., "--voice-wav", help="Voice audio input (wav/mp3/etc)."),
    out: Path = typer.Option(DEFAULT_AUDIO_OUT, "--out", help="Output audio path (wav/mp3)."),
    duration: int | None = typer.Option(
        None, "--duration", help="Total duration in seconds (optional; default: auto minimum)."
    ),
) -> None:
    """Render a UVB-ish audio mix from a voice file using FFmpeg.

    The renderer always produces at least the minimum required duration derived
    from the voice file length plus the configured padding/buzzer windows. If
    `--duration` is provided and is too short, the renderer raises an error.

    Args:
        voice_wav: Path to the voice recording that will be processed and mixed.
        out: Output path for the rendered audio (wav/mp3).
        duration: Optional total duration in seconds.

    Raises:
        typer.Exit: Exit code 1 on domain errors, after printing a message.

    """
    try:
        render_uvb_mix(
            voice_wav=voice_wav,
            out_path=out,
            cfg=AudioRenderConfig(duration_seconds=duration),
        )
        console.print(Panel.fit(f"Wrote:\n- {out}", title="render-audio"))
    except Uvb76GenError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("render-background")
def render_background(
    out: Path = typer.Option(
        Path("out/background.mp3"), "--out", help="Output audio path (wav/mp3)."
    ),
    duration: float = typer.Option(120.0, "--duration", help="Total duration in seconds."),
) -> None:
    """Render a static + buzzer background track (no voice)."""
    try:
        render_background_buzzer(
            out_path=out, cfg=AudioRenderConfig(), duration_seconds=float(duration)
        )
        console.print(Panel.fit(f"Wrote:\n- {out}", title="render-background"))
    except Uvb76GenError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("render-static-voice")
def render_static_voice_cmd(
    voice_wav: Path = typer.Option(..., "--voice-wav", help="Voice audio input (wav/mp3/etc)."),
    out: Path = typer.Option(
        Path("out/static_voice.mp3"), "--out", help="Output audio path (wav/mp3)."
    ),
    intro: float = typer.Option(3.0, "--intro", help="Static-only intro seconds."),
    outro: float = typer.Option(3.0, "--outro", help="Static-only outro seconds."),
) -> None:
    """Render a static + voice track (no buzzer)."""
    try:
        render_static_voice(
            voice_wav=voice_wav,
            out_path=out,
            cfg=AudioRenderConfig(),
            intro_seconds=float(intro),
            outro_seconds=float(outro),
        )
        console.print(Panel.fit(f"Wrote:\n- {out}", title="render-static-voice"))
    except Uvb76GenError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
