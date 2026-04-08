"use strict";
/**
 * build_video.js — FFmpeg compositor for Gita YT videos.
 *
 * Exports (used by run_phase1.py via child_process):
 *   probeAudioDuration(filePath) → Promise<number>  seconds
 *   computeSlides({sanskritDuration, hindiDuration}) → Array<{name, duration}>
 *
 * Slide structure (5 slides):
 *   1. intro           — 1.0s fixed
 *   2. sanskrit        — = audio duration
 *   3. transliteration — 1.5s fixed
 *   4. hindi           — = audio duration
 *   5. outro           — 3.0s fixed
 */

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

// Slide timing constants (seconds)
const INTRO_DURATION = 1.0;
const TRANSLIT_DURATION = 1.5;
const OUTRO_DURATION = 3.0;
const WARN_DURATION = 58; // warn if total > this

/**
 * Probe an audio file and return its duration in seconds.
 * Uses ffprobe with JSON output — no shell injection risk.
 * @param {string} filePath
 * @returns {Promise<number>}
 */
async function probeAudioDuration(filePath) {
  const { ffprobe } = getBins();
  const result = spawnSync(
    ffprobe,
    ["-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", filePath],
    { encoding: "utf8" }
  );

  if (result.status !== 0) {
    const detail = result.error?.message ?? result.stderr ?? "(no details)";
    throw new Error(`ffprobe failed for ${filePath}: ${detail}`);
  }

  let data;
  try {
    data = JSON.parse(result.stdout);
  } catch (e) {
    throw new Error(
      `ffprobe returned invalid JSON for ${filePath}: ${result.stdout.slice(0, 200)}`
    );
  }

  const stream = (data.streams || []).find((s) => s.codec_type === "audio");
  if (!stream) {
    throw new Error(`No audio stream found in ${filePath}`);
  }

  let duration = parseFloat(stream.duration);
  if (isNaN(duration) || duration <= 0) {
    // fallback to format-level duration (present in VBR MP3s and some AAC files)
    duration = parseFloat(data.format?.duration);
  }
  if (isNaN(duration) || duration <= 0) {
    throw new Error(
      `Cannot determine duration for ${filePath}: stream.duration=${stream.duration}, format.duration=${data.format?.duration}`
    );
  }

  return duration;
}

/**
 * Compute slide timing array from audio durations.
 * @param {{sanskritDuration: number, hindiDuration: number}} opts
 * @returns {Array<{name: string, duration: number}>}
 */
function computeSlides({ sanskritDuration, hindiDuration }) {
  if (!isFinite(sanskritDuration) || sanskritDuration <= 0) {
    throw new Error(`computeSlides: invalid sanskritDuration: ${sanskritDuration}`);
  }
  if (!isFinite(hindiDuration) || hindiDuration <= 0) {
    throw new Error(`computeSlides: invalid hindiDuration: ${hindiDuration}`);
  }
  return [
    { name: "intro", duration: INTRO_DURATION },
    { name: "sanskrit", duration: sanskritDuration },
    { name: "transliteration", duration: TRANSLIT_DURATION },
    { name: "hindi", duration: hindiDuration },
    { name: "outro", duration: OUTRO_DURATION },
  ];
}

/**
 * Find the ffmpeg/ffprobe binaries that support drawtext (libfreetype).
 * Prefers ffmpeg-full (keg-only Homebrew) over the default ffmpeg.
 * Returns { ffmpeg, ffprobe } absolute paths.
 */
function findFfmpegBinaries() {
  const candidates = [
    "/opt/homebrew/opt/ffmpeg-full/bin",
    "/usr/local/opt/ffmpeg-full/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
  ];
  for (const dir of candidates) {
    const ffmpeg = path.join(dir, "ffmpeg");
    const ffprobe = path.join(dir, "ffprobe");
    if (fs.existsSync(ffmpeg) && fs.existsSync(ffprobe)) {
      // Check if this ffmpeg has drawtext
      const r = spawnSync(ffmpeg, ["-filters"], { encoding: "utf8" });
      if ((r.stdout || "").includes("drawtext")) {
        return { ffmpeg, ffprobe };
      }
    }
  }
  throw new Error(
    "No ffmpeg with drawtext filter found.\n" +
    "Install with: brew install ffmpeg-full\n" +
    "Then ensure /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg is accessible."
  );
}

// Cache binaries so we only resolve once per process
let _bins = null;
function getBins() {
  if (!_bins) _bins = findFfmpegBinaries();
  return _bins;
}

/**
 * Synchronously probe audio duration. Used internally by buildVideo.
 * (probeAudioDuration is the async public API; this is the sync internal version)
 */
function getAudioDuration(filePath) {
  const { ffprobe } = getBins();
  const result = spawnSync(ffprobe, [
    "-v", "quiet",
    "-print_format", "json",
    "-show_streams",
    "-show_format",
    filePath,
  ], { encoding: "utf8" });

  if (result.status !== 0) {
    const detail = result.error?.message ?? result.stderr ?? "(no details)";
    throw new Error(`ffprobe failed for ${filePath}: ${detail}`);
  }

  let data;
  try {
    data = JSON.parse(result.stdout);
  } catch (e) {
    throw new Error(`ffprobe returned invalid JSON for ${filePath}: ${result.stdout.slice(0, 200)}`);
  }
  const stream = (data.streams || []).find(s => s.codec_type === "audio");
  if (!stream) throw new Error(`No audio stream found in ${filePath}`);

  let dur = parseFloat(stream.duration);
  if (isNaN(dur) || dur <= 0) dur = parseFloat(data.format?.duration);
  if (isNaN(dur) || dur <= 0) throw new Error(`Cannot determine duration for ${filePath}`);
  return dur;
}

/**
 * Compute absolute start/end timestamps for each slide.
 * Returns { slide2Start, slide2End, slide3Start, slide3End,
 *           slide4Start, slide4End, totalDur, warning }
 */
function computeTimings({ sanskritDur, hindiDur }) {
  const slide2Start = INTRO_DURATION;
  const slide2End   = slide2Start + sanskritDur;
  const slide3Start = slide2End;
  const slide3End   = slide3Start + TRANSLIT_DURATION;
  const slide4Start = slide3End;
  const slide4End   = slide4Start + hindiDur;
  const totalDur    = slide4End + OUTRO_DURATION;
  return {
    slide2Start, slide2End,
    slide3Start, slide3End,
    slide4Start, slide4End,
    totalDur,
    warning: totalDur > WARN_DURATION,
  };
}

/**
 * Find the Noto Sans Devanagari font on macOS.
 * Returns the absolute path to the .ttf/.otf file.
 */
function findFont() {
  const candidates = [
    "/Library/Fonts/NotoSansDevanagari-Regular.ttf",
    "/Library/Fonts/NotoSansDevanagari[wdth,wght].ttf",
    "/opt/homebrew/Caskroom/font-noto-sans-devanagari/latest/NotoSansDevanagari[wdth,wght].ttf",
    "/opt/homebrew/share/fonts/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/local/share/fonts/noto/NotoSansDevanagari-Regular.ttf",
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  // fallback: use locate/find
  const r = spawnSync("find", ["/Library/Fonts", "/opt/homebrew", "-name", "*Devanagari*.ttf", "-maxdepth", "6"], { encoding: "utf8" });
  const found = (r.stdout || "").split("\n").filter(Boolean);
  if (found.length) return found[0];
  throw new Error("Noto Sans Devanagari font not found. Install with: brew install --cask font-noto-sans-devanagari");
}

/** Word-wraps text at maxChars per line. */
function wrapText(text, maxChars = 16) {
  const words = text.split(/\s+/);
  const lines = [];
  let cur = "";
  for (const w of words) {
    const joined = cur ? cur + " " + w : w;
    if (joined.length > maxChars && cur) { lines.push(cur); cur = w; }
    else cur = joined;
  }
  if (cur) lines.push(cur);
  return lines;
}

/** Escapes special characters for FFmpeg drawtext filter. */
function esc(t) {
  return t
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\u2019")
    .replace(/:/g, "\\:")
    .replace(/\[/g, "\\[")
    .replace(/\]/g, "\\]")
    .replace(/%/g, "\\%");
}

/** Returns one drawtext filter string. */
function dt({ text, font, size, color, x, y, enable, bold = false }) {
  let f = `drawtext=fontfile='${font}':text='${esc(text)}':fontcolor=${color}` +
          `:fontsize=${size}:x=${x}:y=${y}:enable='${enable}'`;
  if (bold) f += `:borderw=2:bordercolor=${color}`;
  return f;
}

/**
 * Build one MP4 via FFmpeg.
 *
 * @param {{
 *   chapter: number, verse: number,
 *   sanskritText: string, transliteration: string, hindiSummary: string,
 *   sanskritAudio: string, hindiAudio: string, fluteAudio: string,
 *   style: "plain"|"image",
 *   krishnaPoolDir?: string,
 *   outputPath: string
 * }} opts
 */
function buildVideo({ chapter, verse, sanskritText, transliteration, hindiSummary,
                      sanskritAudio, hindiAudio, fluteAudio, style,
                      krishnaPoolDir = "images/krishna-pool", outputPath }) {

  const font        = findFont();
  const sanskritDur = getAudioDuration(sanskritAudio);
  const hindiDur    = getAudioDuration(hindiAudio);
  const t           = computeTimings({ sanskritDur, hindiDur });

  if (t.warning) {
    console.warn(`⚠  WARNING: ${outputPath} is ${t.totalDur.toFixed(1)}s > 58s — shorten Hindi summary`);
  }

  // ── Text overlay filters ──────────────────────────────────────────────
  const LINE_H = 62;
  const filters = [];

  // Top label — 2-line header: brand + chapter reference
  filters.push(dt({ text: "- Bhagavad Gita -",
                    font, size: 28, color: "#FFD700@0.88",
                    x: "(w-text_w)/2", y: "55", enable: "gte(t,0)" }));
  filters.push(dt({ text: `Adhyay ${chapter}  |  Shloka ${verse}`,
                    font, size: 44, color: "white@0.92",
                    x: "(w-text_w)/2", y: "100", enable: "gte(t,0)" }));

  // Slide 2 — Sanskrit (golden, multi-line) — block centred at 65% from top
  const sLines = wrapText(sanskritText, 20);
  sLines.forEach((line, i) =>
    filters.push(dt({ text: line, font, size: 50, color: "#FFD700",
                      x: "(w-text_w)/2",
                      y: `h*0.65-${Math.round(sLines.length * LINE_H / 2)}+${i * LINE_H}`,
                      enable: `between(t,${t.slide2Start},${t.slide2End})` }))
  );

  // Slide 3 — 1.5s silent gap (no text)

  // Slide 4 — Hindi meaning (golden, multi-line) — block centred at 65% from top
  const hLines = wrapText(hindiSummary, 20);
  hLines.forEach((line, i) =>
    filters.push(dt({ text: line, font, size: 46, color: "#FFD700",
                      x: "(w-text_w)/2",
                      y: `h*0.65-${Math.round(hLines.length * LINE_H / 2)}+${i * LINE_H}`,
                      enable: `between(t,${t.slide4Start},${t.slide4End})` }))
  );

  // Slide 5 — Outro call-to-action
  filters.push(dt({ text: "Follow us for more",
                    font, size: 44, color: "white@0.90",
                    x: "(w-text_w)/2", y: "(h-text_h)/2",
                    enable: `between(t,${t.slide4End},${t.totalDur})` }));

  // Watermark text — channel handle (logo overlaid separately via overlay filter)
  filters.push(dt({ text: "@Krishna-GeetaShlokas", font, size: 34, color: "white@0.50",
                    x: "390", y: "h-85", enable: "gte(t,0)" }));

  const textFilters = filters.join(",");

  // ── Background ────────────────────────────────────────────────────────
  const logoPath = path.join(__dirname, "../images/yt-logo.png");
  let bgInputArgs, bgFilter;
  if (style === "plain") {
    bgInputArgs = ["-f", "lavfi", "-i",
                   `color=c=0x0e0508:s=1080x1920:r=30:d=${t.totalDur}`];
    // Slow-breathing golden radial glow centred mid-frame (geq on lavfi color source)
    const geqR = "28+18*sin(2*3.14159*T/9)*exp(-((X-W/2)*(X-W/2)+(Y-H*0.45)*(Y-H*0.45))/(W*W*0.18))+4*sin(2*3.14159*T/3.5)";
    const geqG = "7+5*sin(2*3.14159*T/9)*exp(-((X-W/2)*(X-W/2)+(Y-H*0.45)*(Y-H*0.45))/(W*W*0.18))";
    const geqB = "2+sin(2*3.14159*T/11)";
    bgFilter = `[0:v]geq=r='${geqR}':g='${geqG}':b='${geqB}',drawbox=x=0:y=0:w=iw:h=175:color=black@0.65:t=fill,${textFilters}[vtext]`;
  } else {
    const imgs = fs.readdirSync(krishnaPoolDir).filter(f => /\.jpg$/i.test(f));
    if (!imgs.length) throw new Error(`No images in ${krishnaPoolDir}. Run fetch_krishna_images.py first.`);
    const img = path.join(krishnaPoolDir, imgs[Math.floor(Math.random() * imgs.length)]);
    console.log(`  Image: ${img}`);
    bgInputArgs = ["-loop", "1", "-framerate", "30", "-t", String(t.totalDur), "-i", img];
    bgFilter = `[0:v]scale=1080:1920:force_original_aspect_ratio=increase,` +
               `crop=1080:1920,fps=30,` +
               `eq=saturation=1.4,` +
               `drawbox=x=0:y=0:w=iw:h=ih:color=black@0.60:t=fill,` +
               `drawbox=x=0:y=0:w=iw:h=175:color=black@0.40:t=fill,` +
               `${textFilters}[vtext]`;
  }

  // ── Audio ─────────────────────────────────────────────────────────────
  const s2ms = Math.round(t.slide2Start * 1000);
  const s4ms = Math.round(t.slide4Start * 1000);
  // Note: FFmpeg's filter_complex expression evaluator does not support or().
  // Use gt(a+b,0) to combine two conditions. All commas must be escaped as \,
  // within filter_complex strings (single quotes protect against filter-graph
  // parsing but not expression-level comma splitting in filter options).
  const fluteExpr =
    `if(gt(between(t\\,${t.slide2Start}\\,${t.slide2End})` +
    `+between(t\\,${t.slide4Start}\\,${t.slide4End})\\,0)\\,0.1\\,0.2)`;

  // Logo is input [4:v] (after bg[0], skt[1], hnd[2], flute[3])
  // Scale logo to 55x38 and overlay bottom-center alongside the text
  const filterComplex = [
    bgFilter,
    `[1:a]adelay=${s2ms}|${s2ms},apad=whole_dur=${t.totalDur}[skt]`,
    `[2:a]adelay=${s4ms}|${s4ms},apad=whole_dur=${t.totalDur}[hnd]`,
    `[3:a]aloop=loop=-1:size=2000000000,atrim=0:${t.totalDur},` +
        `volume='${fluteExpr}':eval=frame[flute]`,
    `[skt][hnd][flute]amix=inputs=3:normalize=0:dropout_transition=0[aout]`,
    `[4:v]scale=55:38,format=rgba,colorchannelmixer=aa=0.75[logo]`,
    `[vtext][logo]overlay=x=325:y=H-88[vout]`,
  ].join(";");

  const args = [
    "-y",
    ...bgInputArgs,
    "-i", sanskritAudio,
    "-i", hindiAudio,
    "-i", fluteAudio,
    "-loop", "1", "-i", logoPath,
    "-filter_complex", filterComplex,
    "-map", "[vout]", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
    "-c:a", "aac", "-ar", "44100",
    "-t", String(t.totalDur),
    outputPath,
  ];

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  const { ffmpeg } = getBins();
  const r = spawnSync(ffmpeg, args, { encoding: "utf8", maxBuffer: 20 * 1024 * 1024 });
  if (r.status !== 0) {
    const detail = r.error?.message ?? r.stderr?.slice(-1200) ?? "(no details)";
    throw new Error(`FFmpeg failed:\n${detail}`);
  }
}

module.exports = { probeAudioDuration, computeSlides, WARN_DURATION, getAudioDuration, computeTimings, findFont, buildVideo };

// ── CLI entry point ────────────────────────────────────────────────────────
if (require.main === module) {
  const argv = process.argv.slice(2);
  const get = key => { const i = argv.indexOf("--" + key); return i >= 0 ? argv[i + 1] : null; };
  const req = key => { const v = get(key); if (!v) { console.error(`Missing --${key}`); process.exit(1); } return v; };

  const outputPath = req("output");
  buildVideo({
    chapter:         parseInt(req("chapter"), 10),
    verse:           parseInt(req("verse"), 10),
    sanskritText:    req("sanskrit-text"),
    transliteration: req("transliteration"),
    hindiSummary:    req("hindi-summary"),
    sanskritAudio:   req("sanskrit-audio"),
    hindiAudio:      req("hindi-audio"),
    fluteAudio:      req("flute-audio"),
    style:           req("style"),
    outputPath,
  });
  console.log(`✓ ${outputPath}`);
}
