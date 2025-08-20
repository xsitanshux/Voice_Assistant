class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.port.onmessage = (e) => {
      // every message is an Int16Array
      this.queue.push(new Int16Array(e.data));
    };
    this.cur = null;
    this.idx = 0;
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];          // mono
    for (let i = 0; i < out.length; i++) {
      if (!this.cur || this.idx >= this.cur.length) {
        this.cur = this.queue.shift();
        this.idx = 0;
        if (!this.cur) { out[i] = 0; continue; }
      }
      out[i] = this.cur[this.idx++] / 32768;
    }
    return true;
  }
}

registerProcessor('pcm-player', PCMPlayer);
