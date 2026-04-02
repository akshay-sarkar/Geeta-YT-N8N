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
  const result = spawnSync(
    "ffprobe",
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

module.exports = { probeAudioDuration, computeSlides, WARN_DURATION };
