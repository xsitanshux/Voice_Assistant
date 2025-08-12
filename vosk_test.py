from vosk import Model, KaldiRecognizer
import sounddevice as sd
import queue
import json

model_path = "C:/python/voice_assistant/models/vosk/vosk-model-small-en-us-0.15"
sample_rate = 16000
q = queue.Queue()

def callback(indata, frames, time, status):
    q.put(bytes(indata))

print(" Loading Vosk model...")
model = Model(model_path)  # 
recognizer = KaldiRecognizer(model, sample_rate)

print("Listening... Speak into mic.")
with sd.RawInputStream(samplerate=sample_rate, blocksize=8000, dtype='int16',
                       channels=1, callback=callback):
    while True:
        data = q.get()
        if recognizer.AcceptWaveform(data):
            print(json.loads(recognizer.Result()))
        else:
            print(json.loads(recognizer.PartialResult()))



# import numpy as np
# import sounddevice as sd

# duration = 10  # seconds
# frequency = 440  # A4 note
# sample_rate = 22050

# print("🔊 Playing test tone...")
# t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
# tone = 0.2 * np.sin(2 * np.pi * frequency * t)
# sd.play(tone, samplerate=sample_rate)
# sd.wait()
# print(" Done")
