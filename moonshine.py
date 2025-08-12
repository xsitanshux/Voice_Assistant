import queue
import threading 
import sys
import time
import re
import numpy as np
import sounddevice as sd
import torch
from transformers import pipeline

RATE          = 16_000
BLOCK_SEC     = 0.8             
OVERLAP_SEC   = 0.2            
DEVICE_ID     = None           

model_id = "UsefulSensors/moonshine-tiny"
pipe = pipeline(
    "automatic-speech-recognition",
    model=model_id,
    torch_dtype=torch.float32,
    device="cpu"
)


audio_q   = queue.Queue()
stop_flag = threading.Event()

def transcribe_worker():
    last_tail = ""
    while not stop_flag.is_set():
        chunk = audio_q.get()
        if chunk is None:
            break
        text = pipe(chunk, batch_size=1)["text"].strip().lower()
        # simple de-dupe: drop words that were already printed
        if last_tail:
            overlap = re.escape(last_tail.strip())
            text = re.sub(rf"^{overlap}\s*", "", text)
        print(text, end=" ", flush=True)
        # remember last 3 words for next round
        last_tail = " ".join(text.split()[-3:])

worker = threading.Thread(target=transcribe_worker, daemon=True)
worker.start()

block_size = int(RATE * BLOCK_SEC)
overlap    = int(RATE * OVERLAP_SEC)
buffer     = np.empty(0, dtype=np.float32)

def callback(indata, frames, time_info, status):
    global buffer
    if status: 
        print(status, file=sys.stderr)
    buffer = np.concatenate((buffer, indata[:,0]))   
    while len(buffer) >= block_size:
        chunk = buffer[:block_size]
        buffer = buffer[block_size - overlap:]
        audio_q.put(chunk.copy())

with sd.InputStream(
        samplerate=RATE,
        channels=1,
        dtype='float32',
        blocksize=int(RATE * 0.1),   # 100 ms low-latency capture
        callback=callback,
        device=DEVICE_ID):
    print("🎤 Speak.  Press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping…")

stop_flag.set()
audio_q.put(None)
worker.join()
