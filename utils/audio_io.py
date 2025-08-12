import sounddevice as sd
import numpy as np

def play_audio(audio_array, sample_rate=22050):
    print("🔊 [DEBUG] Trying to play audio...")

    # Log output device info
    try:
        sd.default.device = 3
        print(f"🔊 [DEBUG] Using device ID: {sd.default.device}")
    except Exception as e:
        print(f"❌ [ERROR] Could not query audio output device: {e}")

    # Flatten to mono if stereo
    if audio_array.ndim > 1:
        print("🎧 [DEBUG] Converting stereo to mono")
        audio_array = np.mean(audio_array, axis=1)

    # Normalize audio values
    audio_array = np.clip(audio_array, -1.0, 1.0)

    try:
        sd.play(audio_array, samplerate=sample_rate)
        sd.wait()
        print("✅ [DEBUG] Playback finished.\n")
    except Exception as e:
        print(f"❌ [ERROR] Playback failed: {e}")
