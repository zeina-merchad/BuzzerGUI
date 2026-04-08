import math
import wave
from pathlib import Path

SR = 44100
AMP = 0.8
CHANNELS = 1
SAMPWIDTH = 2


def clamp(x):
    return max(-1.0, min(1.0, x))


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


def silence(dur):
    return [0.0] * int(dur * SR)


def sine(freq, t):
    return math.sin(2 * math.pi * freq * t)


def square(freq, t):
    return 1.0 if sine(freq, t) >= 0 else -1.0


def env_adsr(t, dur, a=0.01, d=0.05, s=0.7, r=0.08):
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
        return 1.0 - (1.0 - s) * (t / d_t)
    t -= d_t
    if t < s_t:
        return s
    t -= s_t
    if t < r_t:
        return s * (1.0 - t / r_t)
    return 0.0


def gen_tone(dur, func):
    return [func(i / SR) for i in range(int(dur * SR))]


def mix(*tracks):
    n = max(len(t) for t in tracks)
    out = [0.0] * n
    for tr in tracks:
        for i, v in enumerate(tr):
            out[i] += v
    peak = max(1e-9, max(abs(x) for x in out))
    if peak > 1.0:
        out = [x / peak for x in out]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# FAST DETERMINISTIC RNG (xorshift32)
# ─────────────────────────────────────────────────────────────────────────────
class RNG:
    def __init__(self, seed=12345):
        self.x = seed & 0xFFFFFFFF or 1

    def next_raw(self):
        self.x ^= (self.x << 13) & 0xFFFFFFFF
        self.x ^= (self.x >> 17) & 0xFFFFFFFF
        self.x ^= (self.x << 5) & 0xFFFFFFFF
        return self.x

    def float(self):  # -1..1
        return (self.next_raw() / 0xFFFFFFFF) * 2.0 - 1.0

    def uniform(self, lo, hi):  # lo..hi
        return lo + (self.float() * 0.5 + 0.5) * (hi - lo)

    def noise_buf(self, n):
        return [self.float() for _ in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# IIR BAND-PASS FILTER (2-pole, no numpy)
# ─────────────────────────────────────────────────────────────────────────────
def bandpass(samples, center_hz, bw_hz):
    w0 = 2 * math.pi * center_hz / SR
    bw_w = 2 * math.pi * bw_hz / SR
    sw0 = math.sin(w0)
    alpha = sw0 * math.sinh(math.log(2) / 2 * bw_w / sw0) if sw0 > 1e-6 else 0.1
    alpha = min(alpha, 0.97)
    cw0 = math.cos(w0)
    b0 = alpha
    b1 = 0.0
    b2 = -alpha
    a0 = 1 + alpha
    a1 = -2 * cw0
    a2 = 1 - alpha
    b0 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    out = [0.0] * len(samples)
    x1 = x2 = y1 = y2 = 0.0
    for i, x0 in enumerate(samples):
        y0 = b0 * x0 + b2 * x2 - a1 * y1 - a2 * y2
        out[i] = y0
        x2 = x1
        x1 = x0
        y2 = y1
        y1 = y0
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIMPLE COMB REVERB  (no numpy — pure Python delay lines)
# ─────────────────────────────────────────────────────────────────────────────
def reverb(samples, room_scale=0.6, wet=0.45, dry=0.75):
    """
    Four parallel comb filters + two all-pass — classic Schroeder reverb.
    room_scale 0..1 controls delay lengths (room size feel).
    """
    # Comb filter delays in samples (prime-ish, scaled by room_scale)
    base_delays = [1557, 1617, 1491, 1422]
    delays = [int(d * (0.5 + 0.5 * room_scale)) for d in base_delays]
    gains = [0.805, 0.827, 0.783, 0.764]

    N = len(samples)

    # Run each comb filter
    comb_outs = []
    for delay, gain in zip(delays, gains):
        buf = [0.0] * delay
        out = [0.0] * N
        idx = 0
        for i in range(N):
            buf_out = buf[idx]
            buf[idx] = samples[i] + buf_out * gain
            out[i] = buf_out
            idx = (idx + 1) % delay
        comb_outs.append(out)

    # Sum combs
    summed = [0.0] * N
    for co in comb_outs:
        for i in range(N):
            summed[i] += co[i] * 0.25

    # Two all-pass filters
    ap_delays = [225, 556]
    ap_gain = 0.5
    sig = summed
    for apd in ap_delays:
        buf = [0.0] * apd
        out = [0.0] * N
        idx = 0
        for i in range(N):
            buf_out = buf[idx]
            v = sig[i] + buf_out * ap_gain
            buf[idx] = v
            out[i] = buf_out - ap_gain * v
            idx = (idx + 1) % apd
        sig = out

    # Mix dry + wet
    result = [0.0] * N
    for i in range(N):
        result[i] = samples[i] * dry + sig[i] * wet
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE REALISTIC HAND CLAP
# ─────────────────────────────────────────────────────────────────────────────
def single_clap(rng: RNG, vol: float = 1.0) -> list:
    DUR = 0.18
    N = int(DUR * SR)

    # Layer 1 — smack transient (bright, ultra-short)
    n1 = rng.noise_buf(N)
    bp1 = bandpass(n1, 4800, 3500)
    L1 = [vol * 1.5 * bp1[i] * math.exp(-i / SR * 900) for i in range(N)]

    # Layer 2 — slap burst (mid-high, 0-15 ms)
    n2 = rng.noise_buf(N)
    bp2 = bandpass(n2, 2400, 2200)
    L2 = []
    for i in range(N):
        t = i / SR
        env = (t / 0.0018) * math.exp(1 - t / 0.0018) if t < 0.08 else 0.0
        L2.append(vol * 1.2 * bp2[i] * max(0.0, min(1.0, env)))

    # Layer 3 — palm resonance (mid, 5-60 ms)
    n3 = rng.noise_buf(N)
    bp3 = bandpass(n3, 1050, 800)
    L3 = [
        vol * 0.9 * bp3[i] * env_adsr(i / SR, DUR, a=0.005, d=0.05, s=0.0, r=0.35)
        for i in range(N)
    ]

    # Layer 4 — body air (low-mid tail)
    n4 = rng.noise_buf(N)
    bp4 = bandpass(n4, 550, 450)
    L4 = [
        vol * 0.5 * bp4[i] * env_adsr(i / SR, DUR, a=0.02, d=0.08, s=0.0, r=0.55)
        for i in range(N)
    ]

    return mix(L1, L2, L3, L4)


# ─────────────────────────────────────────────────────────────────────────────
# CROWD CLAPPING
# ─────────────────────────────────────────────────────────────────────────────
def sfx_crowd_clap(n_clappers=60, duration=2.5, seed=1337) -> list:
    """
    Simulate a large crowd clapping.
    - n_clappers virtual hands
    - Each clapper has its own rate (slightly different BPM), phase offset,
      and volume — creating the dense "wash" of crowd applause
    - Room reverb added on top for arena feel
    - Natural crescendo for first 0.4s, steady body, gentle fade at end
    """
    rng = RNG(seed)
    N = int(duration * SR)
    out = [0.0] * N

    for c in range(n_clappers):
        # Each clapper: random BPM between 2.0–3.2 claps/sec
        rate = rng.uniform(2.0, 3.2)  # claps per second
        phase = rng.uniform(0.0, 1.0 / rate)  # random start phase
        vol_base = rng.uniform(0.28, 0.65)

        t = phase
        while t < duration:
            # Tiny human timing jitter (±25 ms)
            jitter = rng.uniform(-0.025, 0.025)
            t_fire = t + jitter
            if t_fire < 0:
                t += 1.0 / rate
                continue

            # Crescendo envelope: ramp up first 0.4s, full body, fade last 0.3s
            pos = t_fire / duration
            if pos < 0.16:
                crowd_env = pos / 0.16  # ramp up
            elif pos > 0.88:
                crowd_env = (1.0 - pos) / 0.12  # fade out
            else:
                crowd_env = 1.0

            vol = vol_base * crowd_env * rng.uniform(0.85, 1.0)

            clap_rng = RNG(rng.next_raw())  # fresh rng per clap so they differ
            clap = single_clap(clap_rng, vol)

            start = int(t_fire * SR)
            for i, v in enumerate(clap):
                idx = start + i
                if idx < N:
                    out[idx] += v

            t += 1.0 / rate

    # Normalize before reverb
    peak = max(1e-9, max(abs(x) for x in out))
    out = [x / peak * 0.80 for x in out]

    # Add room reverb for arena/hall feel
    print("  applying reverb...")
    out = reverb(out, room_scale=0.72, wet=0.6, dry=0.78)

    # Final normalize
    peak = max(1e-9, max(abs(x) for x in out))
    out = [x / peak * 0.88 for x in out]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ALL OTHER SFX (unchanged)
# ─────────────────────────────────────────────────────────────────────────────


def noise_once(seed):
    x = seed & 0xFFFFFFFF
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5) & 0xFFFFFFFF
    return (x / 0xFFFFFFFF) * 2.0 - 1.0, x


def sfx_buzz():
    dur = 0.35

    def f(t):
        trem = 0.5 + 0.5 * math.sin(2 * math.pi * 18 * t)
        return (
            AMP
            * 0.6
            * square(120, t)
            * trem
            * env_adsr(t, dur, a=0.02, d=0.05, s=0.8, r=0.15)
        )

    return gen_tone(dur, f)


def sfx_correct(sounds_dir: Path = None):
    notes = [523.25, 659.25, 783.99]
    dur_each = 0.12
    arpeggio = []
    for freq in notes:

        def make(freq=freq):
            return gen_tone(
                dur_each,
                lambda t, f=freq: (
                    AMP
                    * 0.7
                    * sine(f, t)
                    * env_adsr(t, dur_each, a=0.01, d=0.03, s=0.5, r=0.2)
                ),
            )

        arpeggio += make()
        arpeggio += silence(0.02)

    # Look for applause.wav in the sounds directory
    search_paths = []
    if sounds_dir:
        search_paths.append(Path(sounds_dir) / "applause.wav")
    search_paths += [
        Path("app") / "core" / "sounds" / "applause.wav",
        Path(__file__).parent / "sounds" / "applause.wav",
        Path(__file__).parent / "applause.wav",
    ]

    applause_path = None
    for p in search_paths:
        if p.exists():
            applause_path = p
            break

    if applause_path:
        print(f"  loading applause from {applause_path}")
        with wave.open(str(applause_path), "rb") as wf:
            n = wf.getnframes()
            raw = wf.readframes(n)
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            claps = []
            for i in range(n):
                v = int.from_bytes(
                    raw[i * ch * sw : i * ch * sw + sw], "little", signed=True
                )
                claps.append(v / 32768.0)
        # Arpeggio first, then applause
        return arpeggio + claps
    else:
        print(
            f"  WARNING: applause.wav not found in any of: {[str(p) for p in search_paths]}"
        )
        print("  generating crowd clap fallback...")
        claps = sfx_crowd_clap(n_clappers=60, duration=2.5, seed=4242)
        if len(arpeggio) < len(claps):
            arpeggio += silence((len(claps) - len(arpeggio)) / SR)
        return mix(arpeggio, claps)


def sfx_wrong():
    dur = 0.35

    def f(t):
        freq = 520 + (180 - 520) * (t / dur)
        return (
            AMP * 0.7 * sine(freq, t) * env_adsr(t, dur, a=0.01, d=0.05, s=0.6, r=0.2)
        )

    tone = gen_tone(dur, f)
    seed = 123456

    def nfunc(t):
        nonlocal seed
        v, s2 = noise_once(seed)
        seed = s2
        return AMP * 0.15 * v * env_adsr(t, 0.12, a=0.001, d=0.02, s=0.0, r=0.2)

    return mix(tone, gen_tone(0.12, nfunc) + silence(dur - 0.12))


def sfx_timer_warning():
    b = lambda: gen_tone(
        0.10,
        lambda t: (
            AMP * 0.6 * sine(880, t) * env_adsr(t, 0.10, a=0.005, d=0.02, s=0.4, r=0.2)
        ),
    )
    return b() + silence(0.07) + b()


def sfx_timer_critical():
    b = lambda: gen_tone(
        0.06,
        lambda t: (
            AMP
            * 0.7
            * sine(1046.5, t)
            * env_adsr(t, 0.06, a=0.004, d=0.015, s=0.3, r=0.2)
        ),
    )
    return b() + silence(0.05) + b() + silence(0.05) + b()


def sfx_start():
    dur = 0.40
    seed = 999

    def nfunc(t):
        nonlocal seed
        v, s2 = noise_once(seed)
        seed = s2
        return (
            AMP
            * 0.25
            * v
            * (0.5 + 0.5 * sine(90, t))
            * env_adsr(t, dur, a=0.02, d=0.08, s=0.4, r=0.25)
        )

    def tonefunc(t):
        return (
            AMP
            * 0.45
            * sine(220 + (660 - 220) * (t / dur), t)
            * env_adsr(t, dur, a=0.01, d=0.05, s=0.6, r=0.25)
        )

    return mix(gen_tone(dur, nfunc), gen_tone(dur, tonefunc))


def sfx_next():
    c = gen_tone(
        0.03,
        lambda t: (
            AMP
            * 0.35
            * square(1800, t)
            * env_adsr(t, 0.03, a=0.001, d=0.01, s=0.0, r=0.2)
        ),
    )
    b = gen_tone(
        0.07,
        lambda t: (
            AMP * 0.45 * sine(740, t) * env_adsr(t, 0.07, a=0.003, d=0.02, s=0.2, r=0.2)
        ),
    )
    return c + silence(0.01) + b


def sfx_point():
    dur = 0.18
    return mix(
        gen_tone(
            dur,
            lambda t: (
                AMP
                * 0.65
                * sine(1320, t)
                * env_adsr(t, dur, a=0.002, d=0.03, s=0.0, r=0.2)
            ),
        ),
        gen_tone(
            dur,
            lambda t: (
                AMP
                * 0.35
                * sine(1760, t)
                * env_adsr(t, dur, a=0.002, d=0.04, s=0.0, r=0.25)
            ),
        ),
    )


def main():
    sounds_dir = Path("app") / "core" / "sounds"
    sounds = {
        "buzz.wav": sfx_buzz(),
        "correct.wav": sfx_correct(sounds_dir),
        "wrong.wav": sfx_wrong(),
        "timer_warning.wav": sfx_timer_warning(),
        "timer_critical.wav": sfx_timer_critical(),
        "start.wav": sfx_start(),
        "next.wav": sfx_next(),
        "point.wav": sfx_point(),
    }
    for name, data in sounds.items():
        write_wav(sounds_dir / name, data)
        print(f"Wrote {sounds_dir / name}  ({len(data) / SR:.2f}s)")
    print("\nDone →", sounds_dir.resolve())


if __name__ == "__main__":
    main()
