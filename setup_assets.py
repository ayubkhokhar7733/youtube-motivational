"""Generate default assets (intro, outro, background music)."""
import os
from config import ASSETS_DIR, INTRO_PATH, OUTRO_PATH, MUSIC_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, FPS
from moviepy import ColorClip, TextClip, CompositeVideoClip


def generate_intro():
    if os.path.exists(INTRO_PATH):
        print("Intro already exists")
        return

    print("Generating intro video...")
    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(15, 20, 35))
    text1 = TextClip(
        text="Your Video",
        font_size=72,
        color="white",
        stroke_color="black",
        stroke_width=3,
        method="label",
    ).with_position("center").with_start(0).with_duration(4)

    text2 = TextClip(
        text="Starts Now",
        font_size=48,
        color="#58a6ff",
        stroke_color="black",
        stroke_width=2,
        method="label",
    ).with_position(("center", VIDEO_HEIGHT // 2 + 60)).with_start(1.5).with_duration(2.5)

    intro = CompositeVideoClip([bg, text1, text2], size=(VIDEO_WIDTH, VIDEO_HEIGHT)).with_duration(4)
    intro.write_videofile(INTRO_PATH, fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast")
    intro.close()
    print("Intro generated")


def generate_outro():
    if os.path.exists(OUTRO_PATH):
        print("Outro already exists")
        return

    print("Generating outro video...")
    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(10, 15, 30))
    thanks = TextClip(
        text="Thanks for Watching!",
        font_size=64,
        color="white",
        stroke_color="black",
        stroke_width=3,
        method="label",
    ).with_position(("center", VIDEO_HEIGHT // 2 - 60)).with_start(0).with_duration(5)

    sub = TextClip(
        text="Subscribe for more content",
        font_size=36,
        color="#3fb950",
        stroke_color="black",
        stroke_width=2,
        method="label",
    ).with_position(("center", VIDEO_HEIGHT // 2 + 40)).with_start(1.5).with_duration(3.5)

    outro = CompositeVideoClip([bg, thanks, sub], size=(VIDEO_WIDTH, VIDEO_HEIGHT)).with_duration(5)
    outro.write_videofile(OUTRO_PATH, fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast")
    outro.close()
    print("Outro generated")


def generate_background_music_placeholder(force=False):
    path = os.path.join(MUSIC_DIR, "background.wav")
    if os.path.exists(path) and not force:
        print("Music files already exist")
        return

    print("Generating rich ambient background soundtrack...")
    import wave
    import struct
    import math
    import numpy as np

    sample_rate = 44100
    duration = 60.0
    n_samples = int(sample_rate * duration)

    # 4-chord documentary ambient progression: Am -> Fmaj7 -> Cmaj -> Em7
    chords = [
        [110.0, 220.0, 261.63, 329.63, 440.0, 523.25],   # Am (A2, A3, C4, E4, A4, C5)
        [87.31, 174.61, 261.63, 329.63, 349.23, 523.25], # Fmaj7 (F2, F3, C4, E4, F4, C5)
        [130.81, 261.63, 329.63, 392.00, 523.25, 659.25],# Cmaj (C3, C4, E4, G4, C5, E5)
        [82.41, 164.81, 246.94, 329.63, 392.00, 493.88],  # Em7 (E2, E3, B3, E4, G4, B4)
    ]
    chord_dur = 15.0  # 15s per chord = 60s total

    t = np.linspace(0, duration, n_samples, endpoint=False)
    audio = np.zeros(n_samples, dtype=np.float32)

    for c_idx, chord_freqs in enumerate(chords):
        c_start = c_idx * chord_dur
        c_end = c_start + chord_dur
        mask = (t >= c_start) & (t < c_end)
        t_local = t[mask] - c_start

        # Smooth envelope (fade in/out over 2s for soft transition)
        env = np.ones_like(t_local)
        fade_samples = int(sample_rate * 2.0)
        if len(t_local) > 2 * fade_samples:
            env[:fade_samples] = np.linspace(0.0, 1.0, fade_samples)
            env[-fade_samples:] = np.linspace(1.0, 0.0, fade_samples)

        chord_signal = np.zeros_like(t_local)
        for i, freq in enumerate(chord_freqs):
            weight = 1.0 / (1.0 + 0.3 * i)
            # Gentle chorus/vibrato
            lfo = 1.0 + 0.003 * np.sin(2 * np.pi * 0.25 * t_local + i)
            sig = np.sin(2 * np.pi * freq * lfo * t_local)
            # Add warm second harmonic
            sig += 0.3 * np.sin(4 * np.pi * freq * t_local)
            chord_signal += sig * weight

        audio[mask] += chord_signal * env * 0.3

    # Add gentle pink-noise-like warm tape warmth / air
    noise = (np.random.rand(n_samples).astype(np.float32) - 0.5) * 0.008
    audio += noise

    # Normalize audio to -1 dBFS (0.89 max amplitude)
    max_amp = np.max(np.abs(audio))
    if max_amp > 0:
        audio = (audio / max_amp) * 0.89

    # Convert to 16-bit PCM WAV (stereo)
    int_audio = (audio * 32767).astype(np.int16)
    stereo_audio = np.column_stack((int_audio, int_audio))

    with wave.open(path, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(stereo_audio.tobytes())

    print(f"[setup_assets] Ambient soundtrack generated successfully: {path} (Duration: {duration}s, Peak: 0.89)")


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)

    generate_intro()
    generate_outro()
    generate_background_music_placeholder()

    print("\nAssets setup complete!")
    print(f"  Intro: {'Ready' if os.path.exists(INTRO_PATH) else 'Not available'}")
    print(f"  Outro: {'Ready' if os.path.exists(OUTRO_PATH) else 'Not available'}")
    print(f"  Music: {'Ready' if any(os.listdir(MUSIC_DIR)) else 'Not available'}")


if __name__ == "__main__":
    main()
