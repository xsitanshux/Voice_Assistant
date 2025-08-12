#!/usr/bin/env python
import asyncio
import json
import struct
import sys

import numpy as np
import sounddevice as sd
import websockets

WS_URL = "ws://127.0.0.1:8000/chat"
PROMPT =  "Tell me a fun fact about Hyderabad."


async def main():
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"prompt": PROMPT}))
        hdr = json.loads(await ws.recv())  # {"sr":24000,"fmt":"pcm_s16le"}
        rate = hdr["sr"]

        with sd.OutputStream(channels=1, samplerate=rate, dtype="int16") as out:
            print("\nLLM:")
            async for msg in ws:
                if isinstance(msg, str):  # JSON with tok
                    tok = json.loads(msg)["tok"]
                    print(tok, end="", flush=True)
                else:  # binary PCM
                    pcm = np.frombuffer(msg, dtype="<i2")
                    out.write(pcm)


if __name__ == "__main__":
    asyncio.run(main())
