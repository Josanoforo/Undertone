const MAX_AUDIO_BYTES = 12 * 1024 * 1024;

function errorFrom(value, fallback = "Audio capture error") {
  return value instanceof Error ? value : new Error(value?.message || fallback);
}

function nowMs() {
  return globalThis.performance?.now?.() ?? Date.now();
}

function makeId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function base64FromBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () =>
      reject(new Error("Could not encode the audio segment"));
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const comma = dataUrl.indexOf(",");
      if (comma < 0) reject(new Error("Invalid internal audio format"));
      else resolve(dataUrl.slice(comma + 1));
    };
    reader.readAsDataURL(blob);
  });
}

function chooseMimeType(Recorder) {
  const preferred = [
    "audio/webm;codecs=opus",
    "audio/ogg;codecs=opus",
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
  ];
  if (typeof Recorder.isTypeSupported !== "function") return "";
  return (
    preferred.find((type) => {
      try {
        return Recorder.isTypeSupported(type);
      } catch {
        return false;
      }
    }) || ""
  );
}

export function createLiveAudioController({
  sendChunk,
  onState = () => {},
  onError = () => {},
  onGap = () => {},
  mediaDevices = globalThis.navigator?.mediaDevices,
  MediaRecorderClass = globalThis.MediaRecorder,
  segmentMs = 8000,
  maxPending = 2,
} = {}) {
  if (typeof sendChunk !== "function")
    throw new TypeError("sendChunk debe ser una funciÃ³n");
  const state = {
    status: "idle",
    active: false,
    capturing: false,
    pending: 0,
    dropped: 0,
    delayed: 0,
    source: null,
    elapsedMs: 0,
    lastCompletedAt: null,
    lastError: null,
    lastErrorName: null,
    run: null,
  };
  let generation = 0,
    stream = null,
    recorder = null,
    timer = null,
    startedAt = 0,
    segmentAt = 0,
    segmentWallStart = "";
  let captureId = "",
    sequence = 0,
    offsetMs = 0,
    queue = Promise.resolve(),
    abortController = null;
  let chunks = [];

  const snapshot = () => ({ ...state });
  function notify() {
    try {
      onState(snapshot());
    } catch {}
  }
  function fail(value, gen = generation) {
    const err = errorFrom(value);
    if (gen === generation) {
      state.lastError = err.message;
      state.lastErrorName = err.name;
      state.status = "error";
      state.active = false;
      state.capturing = false;
      notify();
    }
    if (gen === generation) {
      try {
        onError(err);
      } catch {}
    }
    return err;
  }
  function clearTracks(target) {
    for (const track of target?.getTracks?.() || []) {
      try {
        track.onended = null;
        track.stop();
      } catch {}
    }
  }
  function cleanup(gen, status = "idle") {
    if (gen !== generation) return;
    if (timer !== null) clearTimeout(timer);
    timer = null;
    abortController?.abort();
    abortController = null;
    clearTracks(stream);
    stream = null;
    try {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    } catch {}
    recorder = null;
    chunks = [];
    queue = Promise.resolve();
    state.active = false;
    state.capturing = false;
    state.pending = 0;
    state.status = status;
    state.elapsedMs = startedAt
      ? Math.max(0, Math.round(nowMs() - startedAt))
      : state.elapsedMs;
    notify();
  }
  function stop() {
    if (
      !state.active &&
      !state.capturing &&
      state.status !== "requesting-permission"
    )
      return;
    const wasCapturing = state.capturing;
    const run = state.run;
    const gen = ++generation;
    if (wasCapturing) { try { onGap(run, "interrupted"); } catch {} }
    cleanup(gen, "stopped");
  }

  async function start({
    source = "microphone",
    audienceVisible = false,
    title = "",
    language = "en",
    run = null,
  } = {}) {
    if (
      state.active ||
      state.capturing ||
      state.status === "requesting-permission"
    )
      return snapshot();
    if (!["microphone", "display"].includes(source)) {
      fail(new Error("Fuente de audio no vÃ¡lida"));
      return snapshot();
    }
    if (!mediaDevices || !MediaRecorderClass) {
      fail(new Error("Este navegador no permite capturar audio"));
      return snapshot();
    }
    const gen = ++generation;
    state.run = run;
    state.status = "requesting-permission";
    state.lastError = null;
    state.lastErrorName = null;
    state.source = source;
    state.pending = 0;
    state.dropped = 0;
    state.delayed = 0;
    state.elapsedMs = 0;
    state.lastCompletedAt = null;
    notify();
    try {
      const requested =
        source === "microphone"
          ? await mediaDevices.getUserMedia({ audio: true, video: false })
          : await mediaDevices.getDisplayMedia({ audio: true, video: true });
      if (gen !== generation) {
        clearTracks(requested);
        return snapshot();
      }
      const audioTracks = requested?.getAudioTracks?.() || [];
      if (!audioTracks.length) {
        clearTracks(requested);
        fail(
          new Error(
            "La fuente seleccionada no compartiÃ³ audio; activa la opciÃ³n de audio y vuelve a intentar",
          ),
          gen,
        );
        return snapshot();
      }
      stream = requested;
      // Keep display video alive, while recording only the audio tracks.
      const audioStream =
        typeof MediaStream === "function"
          ? new MediaStream(audioTracks)
          : requested;
      captureId = makeId();
      sequence = 0;
      offsetMs = 0;
      startedAt = nowMs();
      segmentAt = startedAt;
      abortController = new AbortController();
      state.active = true;
      state.capturing = true;
      state.status = "recording";
      notify();
      for (const track of requested.getTracks?.() || [])
        track.onended = () => {
          if (gen === generation) stop();
        };
      const mimeType = chooseMimeType(MediaRecorderClass);
      const createRecorder = () => {
        const instance = mimeType
          ? new MediaRecorderClass(audioStream, { mimeType })
          : new MediaRecorderClass(audioStream);
        chunks = [];
        instance.ondataavailable = (event) => {
          if (event.data?.size) chunks.push(event.data);
        };
        instance.onerror = (event) => {
          if (gen === generation) {
            try { onGap(run, "recording error"); } catch {}
            fail(errorFrom(event.error, "Audio recording failed"), gen);
            cleanup(gen, "error");
          }
        };
        instance.onstop = () => {
          if (gen !== generation || !state.capturing) return;
          const data = chunks;
          chunks = [];
          const ended = nowMs();
          const duration = Math.max(0, Math.round(ended - segmentAt));
          const capturedAt = segmentWallStart;
          segmentAt = ended;
          recorder = null;
          if (data.length)
            enqueueSegment(
              new Blob(data, { type: instance.mimeType || mimeType }),
              duration,
              gen,
              { audienceVisible, title, language, capturedAt, run },
            );
          if (gen === generation && state.capturing)
            beginRecorder(gen, audioStream);
        };
        return instance;
      };
      function beginRecorder(currentGen, audio) {
        if (currentGen !== generation || !state.capturing) return;
        try {
          recorder = createRecorder();
          segmentAt = nowMs();
          segmentWallStart = new Date().toISOString();
          recorder.start();
        } catch (error) {
          fail(error, currentGen);
          cleanup(currentGen, "error");
        }
      }
      beginRecorder(gen, audioStream);
      if (gen === generation && state.capturing)
        timer = setTimeout(
          function rotate() {
            if (gen !== generation || !state.capturing) return;
            if (!recorder || recorder.state === "inactive") {
              timer = setTimeout(rotate, 10);
              return;
            }
            try {
              recorder.stop();
            } catch (error) {
              fail(error, gen);
              cleanup(gen, "error");
              return;
            }
            timer = setTimeout(rotate, Math.max(10, segmentMs));
          },
          Math.max(10, segmentMs),
        );
    } catch (error) {
      if (gen !== generation) return snapshot();
      fail(error, gen);
      cleanup(gen, "error");
    }
    return snapshot();
  }

  function enqueueSegment(blob, durationMs, gen, meta) {
    if (gen !== generation || !state.capturing) return;
    const mimeType = String(blob.type || "")
      .split(";")[0]
      .trim()
      .toLowerCase();
    if (!blob.size) {
      fail(new Error("El segmento grabado estÃ¡ vacÃ­o"), gen);
      cleanup(gen, "error");
      return;
    }
    if (!mimeType.startsWith("audio/")) {
      fail(new Error(`Tipo de audio invÃ¡lido: ${blob.type || "(vacÃ­o)"}`), gen);
      cleanup(gen, "error");
      return;
    }
    const currentPending = state.pending;
    if (currentPending >= maxPending) {
      state.dropped += 1;
      try { onGap(meta.run, "backpressure"); } catch {}
      fail(
        new Error(
          "Transcription is delayed: the pending segment limit was reached",
        ),
        gen,
      );
      cleanup(gen, "error");
      return;
    }
    if (currentPending > 0) state.delayed += 1;
    state.pending += 1;
    state.status = currentPending ? "pending" : "recording";
    notify();
    const chunkId = `${captureId}:${sequence++}`;
    const thisOffset = offsetMs;
    offsetMs += durationMs;
    const capturedAt = meta.capturedAt;
    queue = queue
      .then(async () => {
        if (gen !== generation || !state.capturing) return;
        if (blob.size > MAX_AUDIO_BYTES)
          throw new Error("El segmento supera el lÃ­mite de 12 MiB");
        const audio = await base64FromBlob(blob);
        if (gen !== generation || !state.capturing) return;
        await sendChunk(
          {
            audio,
            mimeType,
            captureId,
            chunkId,
            capturedAt,
            offsetSeconds: thisOffset / 1000,
            consent: true,
            audienceVisible: meta.audienceVisible,
            // Optional compatibility aliases; the backend's dedupe key is captureId + chunkId.
            at: capturedAt,
            offsetMs: thisOffset,
          },
          { signal: abortController?.signal, run: meta.run },
        );
        if (gen === generation && state.capturing)
          state.lastCompletedAt = new Date().toISOString();
      })
      .catch((error) => {
        if (gen === generation && state.capturing) {
          try { onGap(meta.run, "segment failed"); } catch {}
          fail(error, gen);
          cleanup(gen, "error");
        }
      })
      .finally(() => {
        if (gen === generation && state.capturing) {
          state.pending = Math.max(0, state.pending - 1);
          state.status = state.pending ? "pending" : "recording";
          notify();
        }
      });
  }

  return { start, stop, getState: snapshot };
}
