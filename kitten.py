from kittentts import KittenTTS
import soundfile as sf
from kitten_class import KittenVoiceStreamer


# m = KittenTTS("KittenML/kitten-tts-nano-0.1")   # first call downloads weights
# print("Voices:", m.available_voices)

tts   = KittenTTS("KittenML/kitten-tts-nano-0.1")
voice = "expr-voice-2-m"           # pick from tts.available_voices
audio = tts.generate(
    "Welcome to Aiden AI, we build cool shit and have fun while building it",
    voice=voice,
    speed=1.0
)

sf.write("demo.wav", audio, 24_000)  # model outputs 24 kHz PCM
print("Saved demo.wav")
