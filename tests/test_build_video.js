"use strict";
const { describe, it, before } = require("node:test");
const assert = require("assert");
const path = require("path");
const fs = require("fs");

// Add tools/ to require path
const toolsDir = path.join(__dirname, "..", "tools");

function requireTool(name) {
  return require(path.join(toolsDir, name));
}

describe("build_video.js — ffprobe + timing", () => {
  let buildVideo;

  before(() => {
    buildVideo = requireTool("build_video");
  });

  it("probeAudioDuration returns a positive number for a real audio file", async () => {
    // Use any real audio file that exists in the repo
    const fluteDir = path.join(__dirname, "..", "audio-sample-flute");
    const files = fs.readdirSync(fluteDir).filter(f => f.match(/\.(mp3|wav|m4a|aiff)$/i));
    assert.ok(files.length > 0, "Need at least one flute audio file for this test");
    const duration = await buildVideo.probeAudioDuration(path.join(fluteDir, files[0]));
    assert.ok(typeof duration === "number", "duration must be a number");
    assert.ok(duration > 0, "duration must be positive");
  });

  it("computeSlides returns 5 slides with correct fixed durations", () => {
    const timings = buildVideo.computeSlides({
      sanskritDuration: 12.5,
      hindiDuration: 18.3,
    });
    assert.strictEqual(timings.length, 5);
    assert.strictEqual(timings[0].name, "intro");
    assert.strictEqual(timings[0].duration, 1.0);
    assert.strictEqual(timings[1].name, "sanskrit");
    assert.strictEqual(timings[1].duration, 12.5);
    assert.strictEqual(timings[2].name, "transliteration");
    assert.strictEqual(timings[2].duration, 1.5);
    assert.strictEqual(timings[3].name, "hindi");
    assert.strictEqual(timings[3].duration, 18.3);
    assert.strictEqual(timings[4].name, "outro");
    assert.strictEqual(timings[4].duration, 3.0);
  });

  it("computeSlides total duration matches sum of individual slides", () => {
    const timings = buildVideo.computeSlides({
      sanskritDuration: 10,
      hindiDuration: 20,
    });
    const total = timings.reduce((sum, s) => sum + s.duration, 0);
    assert.strictEqual(total, 1.0 + 10 + 1.5 + 20 + 3.0);
  });
});
