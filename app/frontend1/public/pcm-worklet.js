class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.inSR = 44100;        // input sample rate from backend
    this.queue = [];          // FIFO of Int16Array chunks
    this.src = null;          // current chunk (Int16Array) or null
    this.pos = 0.0;           // float index within current chunk

    this.port.onmessage = (e) => {
      const data = e.data;
      if (data && data.type === 'cfg') {
        if (typeof data.inSR === 'number') this.inSR = data.inSR;
        return;
      }
      // otherwise it's an ArrayBuffer with PCM int16 data
      this.queue.push(new Int16Array(data));
    };
  }

  _pullChunkIfNeeded() {
    if (this.src && this.pos < this.src.length) return true;
    this.src = this.queue.shift() || null;
    this.pos = 0.0;
    return !!this.src;
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];      // mono float32
    const outSR = sampleRate;       // device/context SR
    const step = this.inSR / outSR; // input samples per output sample

    for (let i = 0; i < out.length; i++) {
      if (!this._pullChunkIfNeeded()) {
        out[i] = 0;
        continue;
      }

      // Safe: src is guaranteed non-null here
      const i0 = this.pos | 0;
      const i1 = Math.min(i0 + 1, this.src.length - 1);
      const frac = this.pos - i0;
      const s0 = this.src[i0] / 32768;
      const s1 = this.src[i1] / 32768;
      out[i] = s0 + (s1 - s0) * frac;

      this.pos += step;

      // If we run past the end of the current chunk, prep for the next one
      if (this.pos >= this.src.length) {
        this.pos -= this.src.length;   // carry fractional remainder
        this.src = null;               // force a pull next iteration
      }
    }
    return true;
  }
}

registerProcessor('pcm-player', PCMPlayer);