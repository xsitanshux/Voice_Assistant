"""
Gemini 1.5 Flash → MeloTTS → WebSocket (binary PCM s16le)

Protocol:
- Client sends once: {"prompt":"..."} over WS
- Server sends once: {"sr":44100,"fmt":"pcm_s16le"}  (header)
- Then interleaves:
    {"tok":"..."}  (JSON text fragments)
    <binary PCM>   (raw int16 frames)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Iterator, List
import asyncio

import google.generativeai as genai  
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn 


from melo.api import TTS  # pip install git+https://github.com/myshell-ai/MeloTTS.git
from pydantic import BaseModel
from starlette.websockets import WebSocketState


# https://huggingface.co/myshell-ai/MeloTTS-English


LOG = logging.getLogger("backend")

# ─── Config knobs ───────────────────────────────────────────────
MODEL_NAME   = "gemini-1.5-flash"   
SPEECH_SPEED = 0.8                    
MELO_LANG    = "EN"
MELO_SPK     = "EN-BR"            
MAX_CHARS    = 120                 
RETRIES      = 3


# ─── Initialize SDKs once ───────────────────────────────────────

API = "AIzaSyAedaeZ3mlOYbRsJR8f-j1ZrqmynCG2IPA"
genai.configure(api_key=API)
gpt = genai.GenerativeModel(MODEL_NAME)  
melo = TTS(language=MELO_LANG, device="auto")
SPEAKER_ID = melo.hps.data.spk2id[MELO_SPK]
SR = int(melo.hps.data.sampling_rate) 

# ─── Web app shell ──────────────────────────────────────────────
app = FastAPI(title="Gemini→MeloTTS Stream")
app.add_middleware(CORSMiddleware, allow_origins=["*"])



class PromptMsg(BaseModel):
    prompt: str

punct_re = re.compile(r"[.!?]")

# Optional: drop Markdown symbols from audio (keep UI raw)
_non_speech  = re.compile(r"[`*_•·\[\]\(\)<>]+|:[a-z_]+:")
_ws_collapse = re.compile(r"\s{2,}")

def pcm16_from_float(wav: np.ndarray) -> bytes:
    """float32 [-1,1] → little-endian int16 bytes"""
    return (np.clip(wav, -1, 1) * 32767).astype("<i2").tobytes()

def iter_pcm_frames(pcm: bytes, sr: int, frame_ms: int = 40):
    """Yield ~frame_ms sized PCM frames for smooth playback."""
    samples_per = int(sr * frame_ms / 1000.0)
    arr = np.frombuffer(pcm, dtype="<i2")
    for i in range(0, len(arr), samples_per):
        yield arr[i:i + samples_per].tobytes()

def synth_melo_pcm16(phrase: str) -> bytes:
    """Blocking TTS → return PCM16 bytes (to run in a worker thread)."""
    wav = melo.tts_to_file(phrase, SPEAKER_ID, output_path=None, speed=SPEECH_SPEED)
    return pcm16_from_float(wav)


#-------------------------------------------------------------------------------------------------------------------------------------------------------------




def clean_for_voice(text: str) -> str:
    return _ws_collapse.sub(" ", _non_speech.sub(" ", text)).strip()

def float_to_pcm16(arr: np.ndarray) -> bytes:
    return (np.clip(arr, -1, 1) * 32767).astype("<i2").tobytes()

def synth_melo(phrase: str) -> bytes:
    """Synthesize one phrase with MeloTTS and return PCM16 bytes."""
    wav = melo.tts_to_file(
        phrase, SPEAKER_ID, output_path=None, speed=SPEECH_SPEED
    )  # returns float32 mono waveform in memory
    return float_to_pcm16(wav)

def stream_gemini(prompt: str) -> Iterator[str]:
    """
    Yield text fragments from Gemini as they stream in.
    """
    for attempt in range(1, RETRIES + 1):
        try:
            resp = gpt.generate_content(prompt, stream=True)  # streaming API  :contentReference[oaicite:3]{index=3}
            for chunk in resp:
                if chunk.text:
                    yield chunk.text
            return
        except Exception as e:
            if attempt == RETRIES:
                raise ValueError(f"{e}")
                time.sleep(1.5 * attempt)

@app.websocket("/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        req = PromptMsg(**await ws.receive_json())
        # tell client the audio format
        await ws.send_json({"sr": SR, "fmt": "pcm_s16le"})

        buf_raw: List[str] = []
        buf_say: List[str] = []
        char_count = 0

        for frag in stream_gemini(req.prompt):
            await ws.send_json({"tok": frag})

            buf_raw.append(frag)
            say = clean_for_voice(frag)
            if say:
                buf_say.append(say)
                char_count += len(say)

            # ↓↓↓ NEW: also flush on newline-heavy chunks
            need_flush = (
                punct_re.search(frag)
                or ("\n" in frag)
                or (char_count >= MAX_CHARS)
            )

            if need_flush:
                phrase = "".join(buf_say).strip()
                if phrase:
                    # Run the heavy TTS synth off the event loop:
                    pcm = await asyncio.to_thread(synth_melo_pcm16, phrase)

                    # Stream small frames so playback starts immediately:
                    for frame in iter_pcm_frames(pcm, SR, frame_ms=40):
                        await ws.send_bytes(frame)

                buf_raw.clear()
                buf_say.clear()
                char_count = 0

        # tail
        if buf_say:
            phrase = "".join(buf_say).strip()
            if phrase:
                pcm = await asyncio.to_thread(synth_melo_pcm16, phrase)
                for frame in iter_pcm_frames(pcm, SR, frame_ms=40):
                    await ws.send_bytes(frame)

    except WebSocketDisconnect:
        LOG.info("client disconnected")
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()


if __name__ == "__main__":
    

    
    uvicorn.run(app, host="0.0.0.0", port=8000)