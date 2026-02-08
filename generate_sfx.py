import math
import wave
from pathlib import Path

SR = 44100          # sample rate
AMP = 0.8           # 0..1 master amplitude
CHANNELS = 1        # mono
SAMPWIDTH = 2       # 16-bit PCM


def clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def env_adsr(t, dur, a=0.01, d=0.05, s=0.7, r=0.08):
    """Simple ADSR envelope. Times are fractions of duration."""
    a_t = a * dur
    d_t = d * dur
    r_t = r * dur
    s_t = max(0.0, dur - (a_t + d_t + r_t))

    if t < 0:
        return 0.0
    if t < a_t:
        return t / a_t
    t -= a_t
    if t < d_t:
        # decay from 1 -> s
        return 1.0 - (1.0 - s) * (t / d_t)
    t -= d_t
    if t < s_t:
        return s
    t -= s_t
    if t < r_t:
        # release from s -> 0
        return s * (1.0 - (t / r_t))
    return 0.0


def sine(freq, t):
    return math.sin(2 * math.pi * freq * t)


def square(freq, t):
    return 1.0 if sine(freq, t) >= 0 else -1.0


def noise(seed):
    # deterministic "noise" without numpy
    # xorshift32
    x = seed & 0xFFFFFFFF
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5) & 0xFFFFFFFF
    return (x / 0xFFFFFFFF) * 2.0 - 1.0, x


def write_wav(path: Path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPWIDTH)
        wf.setframerate(SR)

        frames = bytearray()
        for s in samples:
            v = int(clamp(s) * 32767)
            frames += v.to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(frames)


def gen_tone(dur, func):
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        out.append(func(t))
    return out


def mix(*tracks):
    n = max(len(t) for t in tracks)
    out = [0.0] * n
    for tr in tracks:
        for i, v in enumerate(tr):
            out[i] += v
    # soft normalize
    peak = max(1e-9, max(abs(x) for x in out))
    if peak > 1.0:
        out = [x / peak for x in out]
    return out


def silence(dur):
    return [0.0] * int(dur * SR)


# -------------------------
# Sound designs (simple, punchy)
# -------------------------

def sfx_buzz():
    # Low buzz: square wave + tremolo for "buzzer"
    dur = 0.35
    def f(t):
        base = 120
        trem = 0.5 + 0.5 * math.sin(2 * math.pi * 18 * t)
        e = env_adsr(t, dur, a=0.02, d=0.05, s=0.8, r=0.15)
        return AMP * 0.6 * square(base, t) * trem * e
    return gen_tone(dur, f)

def sfx_correct():
    # Happy arpeggio (C-E-G) with short chirps
    notes = [523.25, 659.25, 783.99]  # C5 E5 G5
    dur_each = 0.12
    parts = []
    for freq in notes:
        def make(freq=freq):
            def f(t):
                e = env_adsr(t, dur_each, a=0.01, d=0.03, s=0.5, r=0.2)
                return AMP * 0.7 * sine(freq, t) * e
            return gen_tone(dur_each, f)
        parts += make()
        parts += silence(0.02)
    return parts

def sfx_wrong():
    # Descending "wah": two tones down + tiny noise
    dur = 0.35
    def f(t):
        start_f = 520
        end_f = 180
        freq = start_f + (end_f - start_f) * (t / dur)
        e = env_adsr(t, dur, a=0.01, d=0.05, s=0.6, r=0.2)
        return AMP * 0.7 * sine(freq, t) * e
    tone = gen_tone(dur, f)

    # add subtle noise hit
    seed = 123456
    def nfunc(t):
        nonlocal seed
        v, seed2 = noise(seed)
        seed = seed2
        e = env_adsr(t, 0.12, a=0.001, d=0.02, s=0.0, r=0.2)
        return AMP * 0.15 * v * e
    hit = gen_tone(0.12, nfunc) + silence(dur - 0.12)

    return mix(tone, hit)

def sfx_timer_warning():
    # Two warning beeps
    beep = lambda: gen_tone(0.10, lambda t: AMP * 0.6 * sine(880, t) * env_adsr(t, 0.10, a=0.005, d=0.02, s=0.4, r=0.2))
    return beep() + silence(0.07) + beep()

def sfx_timer_critical():
    # Rapid beeps (3)
    beep = lambda: gen_tone(0.06, lambda t: AMP * 0.7 * sine(1046.5, t) * env_adsr(t, 0.06, a=0.004, d=0.015, s=0.3, r=0.2))
    return beep() + silence(0.05) + beep() + silence(0.05) + beep()

def sfx_start():
    # "Kickoff" whoosh-ish: rising noise + tone
    dur = 0.40
    seed = 999
    def nfunc(t):
        nonlocal seed
        v, seed2 = noise(seed)
        seed = seed2
        e = env_adsr(t, dur, a=0.02, d=0.08, s=0.4, r=0.25)
        # high-pass-ish by multiplying with fast sine
        return AMP * 0.25 * v * (0.5 + 0.5 * sine(90, t)) * e
    whoosh = gen_tone(dur, nfunc)

    def tonefunc(t):
        f0, f1 = 220, 660
        freq = f0 + (f1 - f0) * (t / dur)
        e = env_adsr(t, dur, a=0.01, d=0.05, s=0.6, r=0.25)
        return AMP * 0.45 * sine(freq, t) * e
    tone = gen_tone(dur, tonefunc)
    return mix(whoosh, tone)

def sfx_next():
    # Short "click" + tiny blip
    click = gen_tone(0.03, lambda t: AMP * 0.35 * square(1800, t) * env_adsr(t, 0.03, a=0.001, d=0.01, s=0.0, r=0.2))
    blip  = gen_tone(0.07, lambda t: AMP * 0.45 * sine(740, t) * env_adsr(t, 0.07, a=0.003, d=0.02, s=0.2, r=0.2))
    return click + silence(0.01) + blip

def sfx_point():
    # Coin-like: two fast decaying tones
    dur = 0.18
    def f1(t):
        e = env_adsr(t, dur, a=0.002, d=0.03, s=0.0, r=0.2)
        return AMP * 0.65 * sine(1320, t) * e
    def f2(t):
        e = env_adsr(t, dur, a=0.002, d=0.04, s=0.0, r=0.25)
        return AMP * 0.35 * sine(1760, t) * e
    return mix(gen_tone(dur, f1), gen_tone(dur, f2))


def main():
    # IMPORTANT: This must match SoundManager default:
    # Path(__file__).parent/"sounds" where sound_manager.py lives in app/core/
    sounds_dir = Path("app") / "core" / "sounds"

    sounds = {
        "buzz.wav": sfx_buzz(),
        "correct.wav": sfx_correct(),
        "wrong.wav": sfx_wrong(),
        "timer_warning.wav": sfx_timer_warning(),
        "timer_critical.wav": sfx_timer_critical(),
        "start.wav": sfx_start(),
        "next.wav": sfx_next(),
        "point.wav": sfx_point(),
    }

    for name, data in sounds.items():
        write_wav(sounds_dir / name, data)
        print("Wrote", sounds_dir / name)

    print("\nDone. Your SoundManager will now find these files in:")
    print(sounds_dir.resolve())


if __name__ == "__main__":
    main()
