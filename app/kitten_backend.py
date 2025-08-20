# backend.py
"""
Ollama → Kitten-TTS → WebSocket (binary PCM)   –   minimal latency backend
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import struct
import time
from typing import Iterator, List

import httpx
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from kittentts import KittenTTS  # pip install kittentts
from ollama import Client  # pip install "ollama[httpx]"
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState   # ⬅︎ add once at top of file
import contextlib 

# ─────────────────────────── Config ────────────────────────────
OLLAMA_URL = "http://54.242.243.62:11434"  # run `ollama serve`
MODEL_NAME = "llama3.1:8b"  # small = faster
VOICE_ID = "expr-voice-2-f"
SAMPLE_RATE = 24_000  # Kitten native
MAX_TOKENS = 25  # flush cadence
RETRIES = 3
SPEECH_SPEED = 1.25 
LOG = logging.getLogger("backend")

# ─────────────────────────── Helpers ───────────────────────────
punct_re = re.compile(r"[.!?]")


def float_to_pcm16(arr: np.ndarray) -> bytes:
    """Convert -1…1 float32 mono → little-endian int16 bytes"""
    pcm = np.clip(arr, -1, 1) * 32767
    return pcm.astype("<i2").tobytes()


def stream_ollama(                                     # ← CHANGED (use chat)
    client: Client, *, prompt: str, model: str
) -> Iterator[str]:
    """
    Yield tokens from Ollama /chat (stream=True).
    """
    messages = [{"role": "user", "content": prompt}]   # chat format
    for attempt in range(1, RETRIES + 1):
        try:
            for chunk in client.chat(                  # ← CHANGED
                    model=model, messages=messages, stream=True
            ):
                yield chunk["message"]["content"]      # ← CHANGED (token field)
            return
        except httpx.HTTPError as exc:
            LOG.warning("Ollama error: %s (retry %s/%s)", exc, attempt, RETRIES)
            if attempt == RETRIES:
                raise
            time.sleep(1.5 * attempt)


# ─────────────────────────── FastAPI app ───────────────────────
app = FastAPI(title="Kitten TTS Streaming API")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

tts = KittenTTS("KittenML/kitten-tts-nano-0.1")  # singleton
ollama = Client(host=OLLAMA_URL, timeout=httpx.Timeout(90.0, read=90.0))


class PromptMsg(BaseModel):
    prompt: str
    model:  str | None = None



@app.websocket("/chat")
async def chat_socket(ws: WebSocket) -> None:
    """
    WebSocket contract
    ------------------
    • Client → server  (JSON once) : {"prompt": "...", "model": "llama3.1:3b"}
    • Server → client  (JSON)     : {"sr":24000,"fmt":"pcm_s16le"}   ← header
                                   {"tok":"hello"}                  ← token
    • Server → client  (binary)   : raw int16 PCM                   ← audio
    """
    await ws.accept()
    try:
        req = PromptMsg(**await ws.receive_json())
        await ws.send_json({"sr": SAMPLE_RATE, "fmt": "pcm_s16le"})

        token_buf: List[str] = []
        token_count = 0

        for tok in stream_ollama(
            ollama, prompt=req.prompt, model=req.model or MODEL_NAME
        ):
            # 1) live text
            await ws.send_json({"tok": tok})

            token_buf.append(tok)
            token_count += 1
            flush = punct_re.search(tok) or token_count >= MAX_TOKENS
            if flush:
                phrase = "".join(token_buf).strip()
                if phrase:
                    audio = tts.generate(phrase, voice=VOICE_ID, speed=SPEECH_SPEED)
                    await ws.send_bytes(float_to_pcm16(audio))
                token_buf.clear()
                token_count = 0

        # final tail
        if token_buf:
            phrase = "".join(token_buf).strip()
            if phrase:
                audio = tts.generate(phrase, voice=VOICE_ID, speed=SPEECH_SPEED)
                await ws.send_bytes(float_to_pcm16(audio))

    except WebSocketDisconnect:
        LOG.info("Client disconnected")
    except Exception as exc:
        LOG.exception("Stream failed: %s", exc)
    
    finally:
        # close only if the client hasn't already closed the socket
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()


# ──────────────────────────── Run local ────────────────────────
if __name__ == "__main__":
    
    p = argparse.ArgumentParser()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
