# """
# Gemini 1.5 Flash → MeloTTS → WebSocket (binary PCM s16le)

# Protocol:
# - Client sends once: {"prompt":"..."} over WS
# - Server sends header: {"sr":<int>,"fmt":"pcm_s16le","frame_ms":<int>}
# - Then interleaves:
#     {"tok":"..."}  (JSON text fragments)
#     <binary PCM>   (raw int16 frames)
# """

# from __future__ import annotations

# import asyncio
# import logging
# import re
# import time
# from contextlib import asynccontextmanager
# from typing import AsyncGenerator, Iterable, Iterator, List, Optional, Any

# import google.generativeai as genai
# import numpy as np
# from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from starlette.websockets import WebSocketState
# import uvicorn

# # If your Melo build expects MeCab/UniDic, keep these lines;
# # they should be NO-OP now that UniDic is installed.
# import MeCab
# import unidic
# tagger = MeCab.Tagger(f"-d {unidic.DICDIR}")

# from melo.api import TTS  # pip install git+https://github.com/myshell-ai/MeloTTS.git

# LOG = logging.getLogger("backend")
# logging.basicConfig(level=logging.INFO)

# # ─── Config knobs ───────────────────────────────────────────────
# MODEL_NAME   = "gemini-1.5-flash"
# SPEECH_SPEED = 0.8
# MELO_LANG    = "EN"
# MELO_SPK     = "EN-BR"
# RETRIES      = 3

# # Streaming behavior (tuned for fast first sound)
# FIRST_FLUSH_MAX_CHARS = 50      # flush after ~a few words
# NORMAL_FLUSH_MAX_CHARS = 220    # later, larger phrases
# MAX_LATENCY_S = 0.25            # cap silence between flushes
# FIRST_FRAME_MS = 10             # tiny frames for the very first chunk
# STREAM_FRAME_MS = 20            # normal frames after first chunk

# # ─── Initialize SDKs once ───────────────────────────────────────
# # (Inline API key as requested)
# API = "AIzaSyAedaeZ3mlOYbRsJR8f-j1ZrqmynCG2IPA"
# genai.configure(api_key=API)
# gpt = genai.GenerativeModel(MODEL_NAME)

# # Create MeloTTS
# melo = TTS(language=MELO_LANG, device="auto")
# SPEAKER_ID = melo.hps.data.spk2id[MELO_SPK]
# SR = int(melo.hps.data.sampling_rate)  # keep model's native SR to avoid resample cost

# # ─── Web app shell ──────────────────────────────────────────────
# app = FastAPI(title="Gemini→MeloTTS Stream")
# app.add_middleware(CORSMiddleware, allow_origins=["*"])


# # ─── Models / utilities ─────────────────────────────────────────
# class PromptMsg(BaseModel):
#     prompt: str

# punct_re = re.compile(r"[.!?]")  # simple boundary detector
# _non_speech  = re.compile(r"[`*_•·\[\]\(\)<>]+|:[a-z_]+:")  # strip md/emoji markup
# _ws_collapse = re.compile(r"\s{2,}")

# def clean_for_voice(text: str) -> str:
#     return _ws_collapse.sub(" ", _non_speech.sub(" ", text)).strip()

# def pcm16_from_float(wav: np.ndarray) -> bytes:
#     """float32 [-1,1] → little-endian int16 bytes"""
#     return (np.clip(wav, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

# def iter_pcm_frames(pcm: bytes, sr: int, frame_ms: int) -> Iterable[bytes]:
#     """Yield PCM16 frames sized by frame_ms for smooth playback."""
#     samples_per = max(1, int(sr * frame_ms / 1000.0))  # int16 samples per frame
#     arr = np.frombuffer(pcm, dtype="<i2", count=(len(pcm) // 2))
#     for i in range(0, len(arr), samples_per):
#         yield arr[i:i + samples_per].tobytes()

# def synth_melo_pcm16(phrase: str) -> bytes:
#     """
#     Blocking TTS synth → return PCM16 bytes.
#     NOTE: Your Melo build returns a float32 waveform if output_path=None.
#     """
#     wav = melo.tts_to_file(phrase, SPEAKER_ID, output_path=None, speed=SPEECH_SPEED)
#     return pcm16_from_float(wav)

# def stream_gemini(prompt: str) -> Iterator[str]:
#     """
#     Yield text fragments from Gemini as they stream in (sync generator).
#     """
#     backoff = 1.0
#     for attempt in range(1, RETRIES + 1):
#         try:
#             resp = gpt.generate_content(prompt, stream=True)
#             for chunk in resp:
#                 if getattr(chunk, "text", None):
#                     yield chunk.text
#             return
#         except Exception as e:
#             if attempt == RETRIES:
#                 raise
#             time.sleep(backoff)
#             backoff *= 1.6  # gentle backoff


# # ---- adapter: accept async OR sync generators uniformly ----
# async def _aiter_maybe_sync(stream: Any):
#     """Yield items from either an async-iterable or a sync-iterable."""
#     if hasattr(stream, "__aiter__"):
#         async for item in stream:
#             yield item
#     else:
#         for item in stream:
#             yield item
#             await asyncio.sleep(0)  # be cooperative


# # ─── FastAPI lifespan: warm-up to avoid cold-start lag ──────────
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     try:
#         # Warm up Melo so first request is instant
#         await asyncio.to_thread(synth_melo_pcm16, "hello")
#         LOG.info("TTS warmup complete")
#     except Exception as e:
#         LOG.warning(f"TTS warmup skipped: {e}")
#     yield
#     LOG.info("Server shutting down")

# app.router.lifespan_context = lifespan  # attach lifespan


# # ─── Routes ─────────────────────────────────────────────────────
# @app.get("/")
# async def root():
#     return {"ok": True, "sr": SR}

# @app.websocket("/chat")
# async def chat(ws: WebSocket) -> None:
#     await ws.accept()
#     try:
#         LOG.info("connection open")
#         req = PromptMsg(**await ws.receive_json())

#         # Tell client the format; start with tiny frames for fastest first sound
#         await ws.send_json({"sr": SR, "fmt": "pcm_s16le", "frame_ms": FIRST_FRAME_MS})

#         buf_say: List[str] = []
#         char_count = 0
#         first_flush = True
#         last_flush_t = time.monotonic()

#         stream = stream_gemini(req.prompt)
#         async for frag in _aiter_maybe_sync(stream):
#             # Live text to UI
#             await ws.send_json({"tok": frag})

#             say = clean_for_voice(frag)
#             if say:
#                 buf_say.append(say)
#                 char_count += len(say)

#             need_flush = (
#                 punct_re.search(frag) is not None                      # punctuation boundary
#                 or ("\n" in frag)                                       # newline
#                 or (first_flush and char_count >= FIRST_FLUSH_MAX_CHARS) # early kick
#                 or (not first_flush and char_count >= NORMAL_FLUSH_MAX_CHARS)
#                 or (char_count > 0 and (time.monotonic() - last_flush_t) >= MAX_LATENCY_S)  # latency cap
#             )

#             if need_flush:
#                 phrase = " ".join(buf_say).strip()
#                 if phrase:
#                     # Run TTS off the event loop
#                     pcm = await asyncio.to_thread(synth_melo_pcm16, phrase)
#                     use_ms = FIRST_FRAME_MS if first_flush else STREAM_FRAME_MS
#                     for frame in iter_pcm_frames(pcm, SR, frame_ms=use_ms):
#                         await ws.send_bytes(frame)
#                     last_flush_t = time.monotonic()

#                     if first_flush:
#                         first_flush = False
#                         # Notify client we’re switching to normal frame size
#                         await ws.send_json({"sr": SR, "fmt": "pcm_s16le", "frame_ms": STREAM_FRAME_MS})

#                 # reset accumulators
#                 buf_say.clear()
#                 char_count = 0

#         # tail flush
#         if buf_say:
#             phrase = " ".join(buf_say).strip()
#             if phrase:
#                 pcm = await asyncio.to_thread(synth_melo_pcm16, phrase)
#                 for frame in iter_pcm_frames(pcm, SR, frame_ms=STREAM_FRAME_MS):
#                     await ws.send_bytes(frame)

#     except WebSocketDisconnect:
#         LOG.info("client disconnected")
#     except Exception as e:
#         LOG.exception("error in /chat: %s", e)
#     finally:
#         if ws.client_state != WebSocketState.DISCONNECTED:
#             await ws.close()
#         LOG.info("connection closed")


# if __name__ == "__main__":
#     # Run with: uvicorn this_file:app --reload
#     uvicorn.run(app, host="0.0.0.0", port=8000)






"""
Gemini 1.5 Flash → MeloTTS → WebSocket (binary PCM s16le)

Protocol:
- Client sends once: {"prompt":"..."} over WS
- Server sends header: {"sr":<int>,"fmt":"pcm_s16le","frame_ms":<int>}
- Then interleaves:
    {"tok":"..."}  (JSON text fragments)
    <binary PCM>   (raw int16 frames)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from typing import Any, Iterable, Iterator, List, Optional

import google.generativeai as genai
import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.websockets import WebSocketState

# If your Melo build expects MeCab/UniDic, keep these lines.
import MeCab
import unidic
_ = MeCab.Tagger(f"-d {unidic.DICDIR}")  # ensure dictionary is discoverable

from melo.api import TTS  # pip install git+https://github.com/myshell-ai/MeloTTS.git

LOG = logging.getLogger("backend")
logging.basicConfig(level=logging.INFO)

# ─── Config knobs ───────────────────────────────────────────────
MODEL_NAME   = "gemini-1.5-flash"
API_KEY      = "AIzaSyAedaeZ3mlOYbRsJR8f-j1ZrqmynCG2IPA"  # inline, as requested

MELO_LANG    = "EN"
MELO_SPK     = "EN-BR"
SPEECH_SPEED = 0.8
RETRIES      = 3

# Natural boundaries & first-phrase feel
BOUNDARY_RE = re.compile(r"[.,!?]")
FIRST_MIN_WORDS = 4          # first audible phrase must have at least this many words
MAX_CHARS = 220              # safety cap if no punctuation arrives (keeps latency bounded)

# Streaming behavior (fast first sound)
FIRST_FRAME_MS = 10          # tiny frames for the first chunk
STREAM_FRAME_MS = 20         # normal frames afterwards
MAX_LATENCY_S = 0.25         # cap silence between flushes (~250ms)

# ─── Initialize SDKs once ───────────────────────────────────────
genai.configure(api_key=API_KEY)
gpt = genai.GenerativeModel(MODEL_NAME)

# Create MeloTTS (keep model's native SR)
melo = TTS(language=MELO_LANG, device="auto")
SPEAKER_ID = melo.hps.data.spk2id[MELO_SPK]
SR = int(melo.hps.data.sampling_rate)

# ─── FastAPI app ────────────────────────────────────────────────
app = FastAPI(title="Gemini→MeloTTS Stream")
app.add_middleware(CORSMiddleware, allow_origins=["*"])


# ─── Models / utilities ─────────────────────────────────────────
class PromptMsg(BaseModel):
    prompt: str

WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)
_NON_SPEECH  = re.compile(r"[`*_•·\[\]\(\)<>]+|:[a-z_]+:")  # strip md/emoji markup
_WS_COLLAPSE = re.compile(r"\s{2,}")

def clean_for_voice(text: str) -> str:
    return _WS_COLLAPSE.sub(" ", _NON_SPEECH.sub(" ", text)).strip()

def count_words(s: str) -> int:
    return len(WORD_RE.findall(s))

def split_at_last_boundary(text: str) -> tuple[Optional[str], str]:
    """
    Return (phrase_including_boundary, remainder) if a boundary exists,
    else (None, text). Keeps the punctuation on the phrase.
    """
    matches = list(BOUNDARY_RE.finditer(text))
    if not matches:
        return None, text
    idx = matches[-1].end()
    return text[:idx], text[idx:]

def pcm16_from_float(wav: np.ndarray) -> bytes:
    """float32 [-1,1] → little-endian int16 bytes"""
    return (np.clip(wav, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

def iter_pcm_frames(pcm: bytes, sr: int, frame_ms: int) -> Iterable[bytes]:
    """Yield PCM16 frames sized by frame_ms for smooth playback."""
    samples_per = max(1, int(sr * frame_ms / 1000.0))  # int16 samples per frame
    arr = np.frombuffer(pcm, dtype="<i2", count=(len(pcm) // 2))
    for i in range(0, len(arr), samples_per):
        yield arr[i:i + samples_per].tobytes()

def synth_melo_pcm16(phrase: str) -> bytes:
    """
    Synthesize one phrase with MeloTTS and return PCM16 bytes.
    Tries in-memory output (output_path=None). If that returns None on your build,
    falls back to a temp WAV.
    """
    wav = melo.tts_to_file(phrase, SPEAKER_ID, output_path=None, speed=SPEECH_SPEED)
    if isinstance(wav, np.ndarray):
        return pcm16_from_float(wav)

    # Fallback: write to temp file and read back
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        melo.tts_to_file(phrase, SPEAKER_ID, tmp_path, speed=SPEECH_SPEED)
        audio, sr_out = sf.read(tmp_path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio[:, 0]  # force mono
        # If the model SR differs (rare), simple linear resample for speed
        if sr_out != SR:
            n_out = int(round(len(audio) * SR / sr_out))
            if n_out <= 1:
                audio = np.zeros((1,), dtype=np.float32)
            else:
                t_in  = np.linspace(0.0, 1.0, len(audio), endpoint=False, dtype=np.float32)
                t_out = np.linspace(0.0, 1.0, n_out,   endpoint=False, dtype=np.float32)
                audio = np.interp(t_out, t_in, audio).astype(np.float32, copy=False)
        return pcm16_from_float(audio)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

def stream_gemini(prompt: str) -> Iterator[str]:
    """
    Yield assistant text fragments from Gemini (sync generator).
    """
    backoff = 0.8
    for attempt in range(1, RETRIES + 1):
        try:
            resp = gpt.generate_content(prompt, stream=True)
            for chunk in resp:
                if getattr(chunk, "text", None):
                    yield chunk.text
            return
        except Exception as e:
            if attempt == RETRIES:
                raise
            time.sleep(backoff)
            backoff *= 1.7

async def _aiter_maybe_sync(stream: Any):
    """Yield items from either an async-iterable or a sync-iterable."""
    if hasattr(stream, "__aiter__"):
        async for item in stream:
            yield item
    else:
        for item in stream:
            yield item
            await asyncio.sleep(0)  # cooperative


# ─── FastAPI lifespan: warm up TTS to avoid first-request lag ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(synth_melo_pcm16, "hello there.")
        LOG.info("TTS warmup complete")
    except Exception as e:
        LOG.warning(f"TTS warmup skipped: {e}")
    yield
    LOG.info("Server shutting down")

app.router.lifespan_context = lifespan


# ─── Routes ─────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"ok": True, "sr": SR}

@app.websocket("/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        LOG.info("connection open")
        req = PromptMsg(**await ws.receive_json())

        # Tell client the format; start with tiny frames for the first burst
        await ws.send_json({"sr": SR, "fmt": "pcm_s16le", "frame_ms": FIRST_FRAME_MS})

        speak_buf: str = ""      # accumulate speakable text
        first_flush = True
        last_flush_t = time.monotonic()

        stream = stream_gemini(req.prompt)
        async for frag in _aiter_maybe_sync(stream):
            # Live text tokens for UI
            await ws.send_json({"tok": frag})

            say = clean_for_voice(frag)
            if not say:
                continue

            speak_buf += say

            flushed_any = False
            # Flush complete phrases at punctuation; may flush multiple per loop
            while True:
                phrase, remainder = split_at_last_boundary(speak_buf)
                if not phrase:
                    break  # no full phrase yet

                # First audible phrase must have a few words (feels natural)
                if first_flush and count_words(phrase) < FIRST_MIN_WORDS:
                    break

                # Synthesize this complete phrase and stream immediately
                pcm = await asyncio.to_thread(synth_melo_pcm16, phrase)
                use_ms = FIRST_FRAME_MS if first_flush else STREAM_FRAME_MS
                for frame in iter_pcm_frames(pcm, SR, frame_ms=use_ms):
                    await ws.send_bytes(frame)

                if first_flush:
                    first_flush = False
                    # Switch client to normal frame size after first burst
                    await ws.send_json({"sr": SR, "fmt": "pcm_s16le", "frame_ms": STREAM_FRAME_MS})

                speak_buf = remainder
                flushed_any = True
                last_flush_t = time.monotonic()

            # Safety: latency cap if no punctuation comes for a while
            if (
                not flushed_any
                and speak_buf
                and (time.monotonic() - last_flush_t) >= MAX_LATENCY_S
                and (not first_flush or count_words(speak_buf) >= FIRST_MIN_WORDS)
            ):
                pcm = await asyncio.to_thread(synth_melo_pcm16, speak_buf.strip())
                for frame in iter_pcm_frames(pcm, SR, frame_ms=STREAM_FRAME_MS):
                    await ws.send_bytes(frame)
                speak_buf = ""
                last_flush_t = time.monotonic()
                if first_flush:
                    first_flush = False
                    await ws.send_json({"sr": SR, "fmt": "pcm_s16le", "frame_ms": STREAM_FRAME_MS})

        # Tail: speak whatever remains
        tail = speak_buf.strip()
        if tail:
            pcm = await asyncio.to_thread(synth_melo_pcm16, tail)
            for frame in iter_pcm_frames(pcm, SR, frame_ms=STREAM_FRAME_MS):
                await ws.send_bytes(frame)

    except WebSocketDisconnect:
        LOG.info("client disconnected")
    except Exception as e:
        LOG.exception("error in /chat: %s", e)
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
        LOG.info("connection closed")


if __name__ == "__main__":
    # Run: uvicorn this_file:app --reload
    uvicorn.run(app, host="0.0.0.0", port=8000)
