const state = {
  tree: [],
  sample: null,
  waveform: null,
  activeId: null,
  filter: "",
};

const els = {
  tree: document.querySelector("#tree"),
  filter: document.querySelector("#filter"),
  count: document.querySelector("#library-count"),
  title: document.querySelector("#sample-title"),
  path: document.querySelector("#sample-path"),
  badges: document.querySelector("#sample-badges"),
  canvas: document.querySelector("#waveform"),
  waveStatus: document.querySelector("#wave-status"),
  audio: document.querySelector("#audio"),
  analysis: document.querySelector("#analysis"),
  fileMeta: document.querySelector("#file-meta"),
  tags: document.querySelector("#tags"),
};

async function boot() {
  state.tree = await getJson("/api/tree");
  renderTree();
  const sampleId = new URLSearchParams(location.search).get("sample");
  if (sampleId) {
    await selectSample(Number(sampleId));
  }
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function renderTree() {
  els.tree.textContent = "";
  const fragment = document.createDocumentFragment();
  const total = countSamples(state.tree);
  els.count.textContent = `${total} samples`;
  for (const node of state.tree) {
    const child = renderNode(node, 0);
    if (child) fragment.appendChild(child);
  }
  els.tree.appendChild(fragment);
}

function countSamples(nodes) {
  let count = 0;
  for (const node of nodes) {
    if (node.type === "sample") count += 1;
    if (node.children) count += countSamples(node.children);
  }
  return count;
}

function renderNode(node, depth) {
  const needle = state.filter.trim().toLowerCase();
  if (needle && !nodeMatches(node, needle)) return null;

  const wrap = document.createElement("div");
  const button = document.createElement("button");
  button.className = `node ${node.type}`;
  button.style.paddingLeft = `${8 + depth * 10}px`;
  button.textContent = node.type === "folder" ? `▾ ${node.name}` : node.name;
  if (node.id === state.activeId) button.classList.add("active");
  wrap.appendChild(button);

  if (node.type === "sample") {
    button.addEventListener("click", () => selectSample(node.id));
    return wrap;
  }

  const children = document.createElement("div");
  children.className = "children";
  for (const childNode of node.children || []) {
    const child = renderNode(childNode, depth + 1);
    if (child) children.appendChild(child);
  }
  wrap.appendChild(children);
  return wrap;
}

function nodeMatches(node, needle) {
  if (node.name.toLowerCase().includes(needle)) return true;
  return (node.children || []).some((child) => nodeMatches(child, needle));
}

async function selectSample(id) {
  state.activeId = id;
  state.sample = await getJson(`/api/sample?id=${encodeURIComponent(id)}`);
  state.waveform = null;
  history.replaceState(null, "", `?sample=${encodeURIComponent(id)}`);
  renderTree();
  renderSample();
  await loadWaveform(id);
}

function renderSample() {
  const s = state.sample;
  els.title.textContent = s.filename;
  els.path.textContent = s.path;
  els.audio.src = s.audio_url;
  renderBadges(s);
  renderDetails(els.analysis, [
    ["BPM", fmt(s.bpm)],
    ["Key", s.musical_key && s.key_scale ? `${s.musical_key} ${s.key_scale}` : "-"],
    ["Loudness", s.loudness_lufs == null ? "-" : `${s.loudness_lufs} dB`],
    ["Category", s.category || "-"],
    ["Mood", s.mood || "-"],
    ["Vector", s.feature_dim ? `${s.feature_dim} dims` : "-"],
    ["Analyzed", s.analyzed_at || "-"],
  ]);
  renderDetails(els.fileMeta, [
    ["Format", s.format || "-"],
    ["Duration", s.duration_sec == null ? "-" : `${s.duration_sec.toFixed(2)}s`],
    ["Sample rate", s.samplerate ? `${s.samplerate} Hz` : "-"],
    ["Channels", s.channels || "-"],
    ["Size", formatBytes(s.file_size)],
    ["Source", s.source || "-"],
    ["Indexed", s.indexed_at || "-"],
  ]);
  els.tags.textContent = "";
  for (const tag of s.tags || []) {
    const item = document.createElement("span");
    item.className = "tag";
    item.textContent = tag;
    els.tags.appendChild(item);
  }
  if (!s.tags || s.tags.length === 0) {
    els.tags.textContent = "-";
  }
}

function renderBadges(s) {
  els.badges.textContent = "";
  for (const label of [s.category, s.bpm ? `${Math.round(s.bpm)} BPM` : null, s.musical_key]) {
    if (!label) continue;
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = label;
    els.badges.appendChild(badge);
  }
}

function renderDetails(target, rows) {
  target.textContent = "";
  for (const [key, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    target.append(dt, dd);
  }
}

async function loadWaveform(id) {
  els.waveStatus.textContent = "Rendering waveform";
  drawEmpty();
  try {
    state.waveform = await getJson(`/api/waveform?id=${encodeURIComponent(id)}&bins=4096`);
    els.waveStatus.textContent = "";
    drawWaveform();
  } catch (err) {
    els.waveStatus.textContent = String(err.message || err);
    drawEmpty();
  }
}

function drawEmpty() {
  const ctx = resizeCanvas();
  ctx.fillStyle = "#0d0f10";
  ctx.fillRect(0, 0, els.canvas.width, els.canvas.height);
}

function drawWaveform() {
  const data = state.waveform;
  if (!data || !data.peaks) return;

  const ctx = resizeCanvas();
  const w = els.canvas.width;
  const h = els.canvas.height;
  ctx.fillStyle = "#0d0f10";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#24292c";
  ctx.lineWidth = 1;

  const channels = Math.min(data.channels, data.peaks.length);
  const laneGap = 18 * devicePixelRatio;
  const laneHeight = (h - laneGap * Math.max(0, channels - 1)) / channels;
  const maxAmp = maxPeak(data.peaks) || 1;

  for (let ch = 0; ch < channels; ch += 1) {
    const top = ch * (laneHeight + laneGap);
    const mid = top + laneHeight / 2;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(w, mid);
    ctx.stroke();

    ctx.fillStyle = ch === 0 ? "#43c7a9" : "#e3c15f";
    for (let x = 0; x < w; x += 1) {
      const i0 = Math.floor((x / w) * data.bins);
      const i1 = Math.max(i0 + 1, Math.floor(((x + 1) / w) * data.bins));
      let lo = 0;
      let hi = 0;
      let rms = 0;
      for (let i = i0; i < i1 && i < data.bins; i += 1) {
        lo = Math.min(lo, data.peaks[ch][i][0]);
        hi = Math.max(hi, data.peaks[ch][i][1]);
        rms = Math.max(rms, data.rms[ch][i] || 0);
      }
      const yHi = mid - (hi / maxAmp) * laneHeight * 0.46;
      const yLo = mid - (lo / maxAmp) * laneHeight * 0.46;
      ctx.globalAlpha = 0.95;
      ctx.fillRect(x, yHi, 1, Math.max(1, yLo - yHi));
      const yRms = (rms / maxAmp) * laneHeight * 0.28;
      ctx.globalAlpha = 0.32;
      ctx.fillRect(x, mid - yRms, 1, Math.max(1, yRms * 2));
    }
  }
  ctx.globalAlpha = 1;
}

function resizeCanvas() {
  const rect = els.canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * ratio));
  const height = Math.max(1, Math.floor(rect.height * ratio));
  if (els.canvas.width !== width || els.canvas.height !== height) {
    els.canvas.width = width;
    els.canvas.height = height;
  }
  return els.canvas.getContext("2d");
}

function maxPeak(peaks) {
  let max = 0;
  for (const channel of peaks) {
    for (const [lo, hi] of channel) {
      max = Math.max(max, Math.abs(lo), Math.abs(hi));
    }
  }
  return max;
}

function fmt(value) {
  return value == null ? "-" : String(Math.round(value * 100) / 100);
}

function formatBytes(value) {
  if (value == null) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let n = value;
  let u = 0;
  while (n >= 1024 && u < units.length - 1) {
    n /= 1024;
    u += 1;
  }
  return `${n.toFixed(u === 0 ? 0 : 1)} ${units[u]}`;
}

els.filter.addEventListener("input", () => {
  state.filter = els.filter.value;
  renderTree();
});
window.addEventListener("resize", drawWaveform);
boot().catch((err) => {
  els.waveStatus.textContent = String(err.message || err);
});
