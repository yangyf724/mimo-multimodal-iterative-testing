const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

test("scene json is valid and has layers", () => {
  const scene = JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "canvas", "promo.scene.json"), "utf8")
  );
  assert.equal(scene.scene_id, "promo-banner");
  assert.ok(Array.isArray(scene.layers) && scene.layers.length >= 3);
  assert.equal(scene.export_target.width, scene.width);
});

test("export size matches scene", () => {
  const scene = JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "canvas", "promo.scene.json"), "utf8")
  );
  assert.equal(scene.export_target.height, scene.height);
});
