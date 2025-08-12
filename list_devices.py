from kittentts import KittenTTS
import soundfile as sf



m = KittenTTS("KittenML/kitten-tts-nano-0.1")   # first call downloads weights
print("Voices:", m.available_voices)