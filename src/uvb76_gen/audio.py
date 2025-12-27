"""uvb76_gen.audio.

FFmpeg-based audio rendering helpers.

This module is responsible for turning a dry voice recording into a UVB-76-ish
radio mix by layering three independent audio sources:

1) Voice track (from a user-provided file)
2) Continuous pink-noise bed (static) across the entire timeline
3) Synthetic "buzzer" tone that is *gated* to play only in specific windows

The renderer builds a single FFmpeg `filter_complex` graph that:

- probes the input voice duration via `ffprobe`,
- computes the required total output duration (minimum timeline),
- optionally validates a user-requested duration,
- time-aligns the voice and buzzer by applying delays,
- mixes everything together with a limiter.

Timeline model (minimum)
------------------------
The minimum output duration is:

    5s  static-only intro  +
    9s  buzzer window      +
    3s  static-only gap    +
    voice_len              +
    3s  static-only gap    +
    9s  buzzer window      +
    5s  static-only outro

Where:
- "static-only" means *only the pink-noise bed is audible* (no voice, no buzzer).
- "buzzer window" means buzzer is periodically on/off inside that window
  (controlled by `buzzer_period_s` and `buzzer_on_s`).
- `voice_len` is derived from `ffprobe`.

Duration behavior
-----------------
- If `AudioRenderConfig.duration_seconds` is None:
  the output duration is exactly the computed minimum.
- If `duration_seconds` is set and is greater than the minimum:
  the extra time is inserted into the post-voice gap (before the ending buzzer).
- If `duration_seconds` is set and is less than the minimum:
  an error is raised and the minimum required duration is reported.

Audio design notes
------------------
- The pink-noise bed is present for the entire output (it provides the "radio"
  texture), but the voice/buzzer are absent during the intro/outro segments.
- Voice processing aims to emulate a narrow-band, compressed, slightly "dirty"
  transmission (high/low-pass, compression, soft clipping, tremolo, echo).
- Buzzer is synthesized via `aevalsrc` (harmonic stack) and then degraded with
  clipping and bit crushing to get a harsher, more "broadcast" tone.
- The final mix is limited to avoid digital clipping.

Requirements
------------
- `ffmpeg` and `ffprobe` must be available on PATH.
- Input voice path must exist.

"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import Uvb76GenError


@dataclass(frozen=True)
class AudioRenderConfig:
    """Configuration for FFmpeg-based UVB-ish audio rendering.

    Attributes:
        duration_seconds:
            Optional total output duration in seconds.

            - If None: produce exactly the computed minimum timeline duration.
            - If set and > minimum: extend the post-voice gap by the extra time.
            - If set and < minimum: raise an error stating the required minimum.

        sample_rate:
            Target sample rate for the rendered output (Hz). The voice is resampled
            to this rate before effects to keep the filter graph consistent.

        mono:
            If True, output is forced to mono.

        static_intro_seconds:
            Duration of the initial "static-only" segment (seconds).
            During this interval only the noise bed is audible.

        static_outro_seconds:
            Duration of the final "static-only" segment (seconds).

        gap_before_voice_seconds:
            Static-only gap between the start buzzer window and the voice start.

        gap_after_voice_seconds:
            Static-only gap between the voice end and the ending buzzer window.
            Any user-requested extra duration is added to this gap.

        voice_gain:
            Linear gain applied to the voice chain before saturation.

        noise_gain:
            Linear amplitude for the pink-noise generator.

        buzzer_gain:
            Linear gain applied to the buzzer after gating (before distortion).

        voice_softclip_threshold / voice_softclip_output:
            Parameters for `asoftclip` on the voice chain (tanh soft clipping),
            used as mild saturation.

        voice_tremolo_freq_hz / voice_tremolo_depth:
            Tremolo settings for the voice:
            - higher freq -> faster amplitude modulation
            - higher depth -> stronger modulation

        voice_reverb_in_gain / voice_reverb_out_gain / voice_reverb_delays_ms / voice_reverb_decays:
            Parameters for `aecho`, used as a simple reverb/echo approximation.

        buzzer_f0_hz:
            Fundamental for the buzzer harmonic stack (Hz). The harmonic expression
            actually builds multiples of this fundamental.

        buzzer_period_s / buzzer_on_s:
            Gating parameters inside each buzzer window:
            - each period is `buzzer_period_s` seconds
            - buzzer is ON for the first `buzzer_on_s` seconds of each period

        buzzer_edge_cycles:
            Number of gate periods to run at the beginning and end.
            The buzzer window length becomes:
                edge = buzzer_edge_cycles * buzzer_period_s

        buzzer_crush_bits:
            Bit depth for `acrusher`. Lower values produce harsher digital artifacts.

        buzzer_softclip_threshold / buzzer_softclip_output:
            Parameters for `asoftclip` on the buzzer chain (hard clipping),
            used to increase grit/harshness.

        buzzer_drive:
            Pre-clip drive multiplier for buzzer distortion.

        buzzer_post_gain:
            Post-processing gain to tame buzzer loudness after distortion/crushing.

    Timeline (minimum):
        5s static-only +
        9s buzzer (edge window) +
        3s static-only gap +
        voice (voice_len) +
        3s static-only gap +
        9s buzzer (edge window) +
        5s static-only

    """

    # If None -> exactly computed minimum. If provided -> must be >= minimum.
    duration_seconds: float | None = None

    sample_rate: int = 44100
    mono: bool = True

    # Static-only padding
    static_intro_seconds: float = 5.0
    static_outro_seconds: float = 5.0

    # Gaps (static-only)
    gap_before_voice_seconds: float = 3.0
    gap_after_voice_seconds: float = 3.0

    voice_gain: float = 2.0
    noise_gain: float = 0.4
    buzzer_gain: float = 0.25

    voice_softclip_threshold: float = 0.85
    voice_softclip_output: float = 1.45
    voice_tremolo_freq_hz: float = 4.5
    voice_tremolo_depth: float = 0.35
    voice_reverb_in_gain: float = 0.8
    voice_reverb_out_gain: float = 0.9
    voice_reverb_delays_ms: str = "55|110"
    voice_reverb_decays: str = "0.20|0.12"

    # Buzzer synthesis + gating
    buzzer_f0_hz: float = 110.7
    buzzer_period_s: float = 3.0
    buzzer_on_s: float = 1.0
    buzzer_edge_cycles: int = 3

    buzzer_crush_bits: int = 2  # radio hell
    buzzer_softclip_threshold: float = 0.05
    buzzer_softclip_output: float = 6.0
    buzzer_drive: float = 12.0
    buzzer_post_gain: float = 0.7


def _probe_duration_seconds(path: Path) -> float:
    """Probe and return an audio file's duration in seconds using ffprobe.

    Args:
        path:
            Path to an audio file readable by ffprobe.

    Returns:
        The duration as a float (seconds).

    Raises:
        Uvb76GenError:
            If ffprobe fails or its output cannot be parsed.

    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Uvb76GenError(f"ffprobe failed:\n{res.stderr}")

    try:
        return float(res.stdout.strip())
    except ValueError as exc:
        raise Uvb76GenError(f"Failed to parse ffprobe duration output: {res.stdout!r}") from exc


def render_uvb_mix(voice_wav: Path, out_path: Path, cfg: AudioRenderConfig) -> None:
    """Render a UVB-ish mix (voice + static + buzzer) using FFmpeg.

    The function:
    - validates the voice file exists,
    - probes voice duration via ffprobe,
    - computes the minimum required output duration based on the configured timeline,
    - validates/adjusts the user-requested duration (if any),
    - builds an FFmpeg filter graph to:
      - process voice (band-limit, compress, saturate, tremolo, echo),
      - generate continuous pink noise across the full duration,
      - synthesize and gate a buzzer in two edge windows,
      - mix and limit the final output,
    - writes the resulting audio to `out_path`.

    Args:
        voice_wav:
            Path to the voice audio file (wav/mp3/etc) to embed into the mix.
        out_path:
            Output audio path. Format is inferred from the file extension.
        cfg:
            Rendering configuration.

    Raises:
        Uvb76GenError:
            If voice file is missing, duration is too short, ffprobe fails,
            or ffmpeg fails.

    """
    if voice_wav.exists() is False:
        raise Uvb76GenError(f"Voice file not found: {voice_wav}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    sr = int(cfg.sample_rate)
    voice_len = _probe_duration_seconds(voice_wav)

    intro = float(cfg.static_intro_seconds)
    outro = float(cfg.static_outro_seconds)
    edge = float(cfg.buzzer_edge_cycles) * float(cfg.buzzer_period_s)

    gap_before = float(cfg.gap_before_voice_seconds)
    gap_after = float(cfg.gap_after_voice_seconds)

    # Minimum timeline:
    # intro + start_buzzer(edge) + gap_before + voice_len + gap_after + end_buzzer(edge) + outro
    computed_min = intro + edge + gap_before + voice_len + gap_after + edge + outro

    if cfg.duration_seconds is None:
        total_d = computed_min
        extra = 0.0
    else:
        requested = float(cfg.duration_seconds)
        if requested < computed_min:
            raise Uvb76GenError(
                f"Duration too short: {requested:.2f}s. "
                f"Minimum required is {computed_min:.2f}s "
                f"(voice={voice_len:.2f}s + 34.00s padding)."
            )
        total_d = requested
        extra = requested - computed_min

    # Add extra time into the post-voice gap (before end buzzer)
    gap_after_effective = gap_after + extra

    # Key timestamps
    voice_start = intro + edge + gap_before
    voice_end = voice_start + voice_len

    end_buzzer_start = voice_end + gap_after_effective
    # end_buzzer_end = end_buzzer_start + edge  # implied
    # total_d should equal end_buzzer_end + outro

    # ---- Voice chain: trim to voice_len, resample, apply fx, delay into the timeline
    voice_chain = ",".join(
        [
            f"atrim=0:{voice_len}",
            "asetpts=N/SR/TB",
            f"aresample={sr}:resampler=soxr",
            "highpass=f=200",
            "lowpass=f=3000",
            "acompressor=threshold=-18dB:ratio=3:attack=10:release=120",
            f"volume={float(cfg.voice_gain)}",
            (
                "asoftclip="
                f"type=tanh:threshold={float(cfg.voice_softclip_threshold)}:"
                f"output={float(cfg.voice_softclip_output)}:oversample=4"
            ),
            f"tremolo=f={float(cfg.voice_tremolo_freq_hz)}:d={float(cfg.voice_tremolo_depth)}",
            (
                "aecho="
                f"{float(cfg.voice_reverb_in_gain)}:{float(cfg.voice_reverb_out_gain)}:"
                f"{cfg.voice_reverb_delays_ms}:{cfg.voice_reverb_decays}"
            ),
            f"adelay={int(round(voice_start * 1000))}|{int(round(voice_start * 1000))}",
        ]
    )

    # ---- Noise chain: full-length bed (first/last 5s become "only noise")
    noise_chain = ",".join(
        [
            f"anoisesrc=d={total_d}:c=pink:r={sr}:a={float(cfg.noise_gain)}",
            "highpass=f=150",
            "lowpass=f=4000",
        ]
    )

    # ---- Buzzer chain: aevalsrc full-length; gated only in the two 9s windows
    period = float(cfg.buzzer_period_s)
    on_s = float(cfg.buzzer_on_s)

    # start window: [intro, intro+edge)
    # end window:   [end_buzzer_start, end_buzzer_start+edge)
    gate_expr = (
        f"(if(gte(t,{intro})*lt(t,{intro + edge}),"
        f" if(lt(mod(t-{intro},{period}),{on_s}),1,0),0)"
        f"+"
        f" if(gte(t,{end_buzzer_start})*lt(t,{end_buzzer_start + edge}),"
        f" if(lt(mod(t-{end_buzzer_start},{period}),{on_s}),1,0),0))"
    )

    f0 = float(cfg.buzzer_f0_hz)
    harm = (
        f"0.64*sin(2*PI*{2 * f0:.4f}*t)+"
        f"1.00*sin(2*PI*{3 * f0:.4f}*t)+"
        f"0.80*sin(2*PI*{4 * f0:.4f}*t)+"
        f"0.50*sin(2*PI*{5 * f0:.4f}*t)+"
        f"0.42*sin(2*PI*{6 * f0:.4f}*t)+"
        f"0.26*sin(2*PI*{7 * f0:.4f}*t)+"
        f"0.28*sin(2*PI*{8 * f0:.4f}*t)+"
        f"0.32*sin(2*PI*{9 * f0:.4f}*t)"
    )

    buzzer_chain = ",".join(
        [
            f"aevalsrc='{harm}':s={sr}:d={total_d}",
            f"volume='({gate_expr})*{float(cfg.buzzer_gain)}':eval=frame",
            f"volume={float(cfg.buzzer_drive)}",
            (
                "asoftclip="
                f"type=hard:threshold={float(cfg.buzzer_softclip_threshold)}:"
                f"output={float(cfg.buzzer_softclip_output)}:oversample=4"
            ),
            f"acrusher=bits={int(cfg.buzzer_crush_bits)}:mix=1.0",
            f"volume={float(cfg.buzzer_post_gain)}",
            "highpass=f=80",
            "lowpass=f=1800",
        ]
    )

    filter_complex = ";".join(
        [
            f"[0:a]{voice_chain}[v]",
            f"{noise_chain}[n]",
            f"{buzzer_chain}[b]",
            "[n][b][v]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.98[out]",
        ]
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_wav),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
    ]

    if cfg.mono is True:
        cmd.extend(["-ac", "1"])

    cmd.extend(["-ar", str(sr), str(out_path)])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Uvb76GenError(f"FFmpeg failed:\n{res.stderr}")


def _buzzer_harm_expr(f0_hz: float) -> str:
    """Return the harmonic-stack expression used by the synthetic buzzer."""
    f0 = float(f0_hz)
    return (
        f"0.64*sin(2*PI*{2 * f0:.4f}*t)+"
        f"1.00*sin(2*PI*{3 * f0:.4f}*t)+"
        f"0.80*sin(2*PI*{4 * f0:.4f}*t)+"
        f"0.50*sin(2*PI*{5 * f0:.4f}*t)+"
        f"0.42*sin(2*PI*{6 * f0:.4f}*t)+"
        f"0.26*sin(2*PI*{7 * f0:.4f}*t)+"
        f"0.28*sin(2*PI*{8 * f0:.4f}*t)+"
        f"0.32*sin(2*PI*{9 * f0:.4f}*t)"
    )


def render_background_buzzer(
    out_path: Path, cfg: AudioRenderConfig, duration_seconds: float = 120.0
) -> None:
    """Render a static + buzzer background track (no voice).

    The buzzer is gated for the full duration:
    1s ON, 1s OFF, repeating for the entire timeline.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sr = int(cfg.sample_rate)
    total_d = float(duration_seconds)
    if total_d <= 0:
        raise Uvb76GenError("duration_seconds must be > 0.")

    # 1s on, 1s off => period=2, on=1
    gate_expr = "if(lt(mod(t,2),1),1,0)"

    harm = _buzzer_harm_expr(cfg.buzzer_f0_hz)

    noise_chain = ",".join(
        [
            f"anoisesrc=d={total_d}:c=pink:r={sr}:a={float(cfg.noise_gain)}",
            "highpass=f=150",
            "lowpass=f=4000",
        ]
    )

    buzzer_chain = ",".join(
        [
            f"aevalsrc='{harm}':s={sr}:d={total_d}",
            f"volume='({gate_expr})*{float(cfg.buzzer_gain)}':eval=frame",
            f"volume={float(cfg.buzzer_drive)}",
            (
                "asoftclip="
                f"type=hard:threshold={float(cfg.buzzer_softclip_threshold)}:"
                f"output={float(cfg.buzzer_softclip_output)}:oversample=4"
            ),
            f"acrusher=bits={int(cfg.buzzer_crush_bits)}:mix=1.0",
            f"volume={float(cfg.buzzer_post_gain)}",
            "highpass=f=80",
            "lowpass=f=1800",
        ]
    )

    filter_complex = ";".join(
        [
            f"{noise_chain}[n]",
            f"{buzzer_chain}[b]",
            "[n][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.98[out]",
        ]
    )

    cmd = [
        "ffmpeg",
        "-y",
        # Dummy input (we generate everything in filter_complex)
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r={sr}:cl=mono",
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
    ]

    if cfg.mono is True:
        cmd.extend(["-ac", "1"])
    cmd.extend(["-ar", str(sr), str(out_path)])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Uvb76GenError(f"FFmpeg failed:\n{res.stderr}")


def render_static_voice(
    voice_wav: Path,
    out_path: Path,
    cfg: AudioRenderConfig,
    intro_seconds: float = 3.0,
    outro_seconds: float = 3.0,
) -> None:
    """Render a static + voice track (no buzzer).

    Timeline:
      intro_seconds  static-only +
      voice_len      (voice + static) +
      outro_seconds  static-only
    """
    if voice_wav.exists() is False:
        raise Uvb76GenError(f"Voice file not found: {voice_wav}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    sr = int(cfg.sample_rate)
    voice_len = _probe_duration_seconds(voice_wav)

    intro = float(intro_seconds)
    outro = float(outro_seconds)
    if intro < 0 or outro < 0:
        raise Uvb76GenError("intro_seconds and outro_seconds must be >= 0.")

    total_d = intro + voice_len + outro

    voice_chain = ",".join(
        [
            f"atrim=0:{voice_len}",
            "asetpts=N/SR/TB",
            f"aresample={sr}:resampler=soxr",
            "highpass=f=200",
            "lowpass=f=3000",
            "acompressor=threshold=-18dB:ratio=3:attack=10:release=120",
            f"volume={float(cfg.voice_gain)}",
            (
                "asoftclip="
                f"type=tanh:threshold={float(cfg.voice_softclip_threshold)}:"
                f"output={float(cfg.voice_softclip_output)}:oversample=4"
            ),
            f"tremolo=f={float(cfg.voice_tremolo_freq_hz)}:d={float(cfg.voice_tremolo_depth)}",
            (
                "aecho="
                f"{float(cfg.voice_reverb_in_gain)}:{float(cfg.voice_reverb_out_gain)}:"
                f"{cfg.voice_reverb_delays_ms}:{cfg.voice_reverb_decays}"
            ),
            f"adelay={int(round(intro * 1000))}|{int(round(intro * 1000))}",
        ]
    )

    noise_chain = ",".join(
        [
            f"anoisesrc=d={total_d}:c=pink:r={sr}:a={float(cfg.noise_gain)}",
            "highpass=f=150",
            "lowpass=f=4000",
        ]
    )

    filter_complex = ";".join(
        [
            f"[0:a]{voice_chain}[v]",
            f"{noise_chain}[n]",
            "[n][v]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.98[out]",
        ]
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_wav),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
    ]

    if cfg.mono is True:
        cmd.extend(["-ac", "1"])
    cmd.extend(["-ar", str(sr), str(out_path)])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Uvb76GenError(f"FFmpeg failed:\n{res.stderr}")
