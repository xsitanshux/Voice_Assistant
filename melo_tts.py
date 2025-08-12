import re
import time
import numpy as np
import sounddevice as sd
from melo.api import TTS  # MeloTTS

# ─── Config you can tweak ─────────────────────────────────────
LANGUAGE     = "EN"          # EN, ES, FR, ZH, JP, KR
SPEAKER_NAME = "EN-US"    # EN-US, EN-BR, EN-Default, EN-AU, EN_INDIA, ...
SPEED        = 1.15          # 1.0 = normal; try 0.9..1.3

# A few sentences to hear quality/latency
SENTENCES = [
"i cannot live without eating chicken"
]

# ─── Helpers ──────────────────────────────────────────────────
def to_pcm16_bytes(wav_f32: np.ndarray) -> bytes:
    wav_f32 = np.clip(wav_f32, -1.0, 1.0)
    return (wav_f32 * 32767.0).astype("<i2").tobytes()

def chunk_bytes(pcm16: bytes, sr: int, chunk_ms: int = 40):
    """Yield ~chunk_ms sized frames for smooth playback."""
    samples_per = int(sr * (chunk_ms / 1000.0))
    arr = np.frombuffer(pcm16, dtype="<i2")
    for i in range(0, len(arr), samples_per):
        yield arr[i:i + samples_per].tobytes()

# ─── Main ─────────────────────────────────────────────────────
def main():
    # Load once (CPU is fine; it will auto-pick GPU if available)
    t0 = time.time()
    tts = TTS(language=LANGUAGE, device="auto")
    spk2id = tts.hps.data.spk2id  # map of speakers per language (e.g., 'EN_INDIA')
    sr = int(tts.hps.data.sampling_rate)  # Melo is typically 44100 Hz
    speaker_id = spk2id[SPEAKER_NAME]
    print(f"Loaded MeloTTS in {time.time()-t0:.2f}s | SR={sr} | speaker={SPEAKER_NAME}")

    # Simple playback stream
    with sd.OutputStream(channels=1, samplerate=sr, dtype="int16") as out:
        for sent in SENTENCES:
            sent = sent.strip()
            if not sent:
                continue

            # Synthesize to memory: output_path=None returns a NumPy waveform
            wav = tts.tts_to_file(sent, speaker_id, output_path=None, speed=SPEED)
            pcm = to_pcm16_bytes(wav)

            print(f"▶ {sent}")
            # Stream in ~40 ms frames so you hear it start quickly
            for frame in chunk_bytes(pcm, sr, chunk_ms=40):
                out.write(np.frombuffer(frame, dtype="<i2"))
        print("✅ Done.")

if __name__ == "__main__":
    main()
