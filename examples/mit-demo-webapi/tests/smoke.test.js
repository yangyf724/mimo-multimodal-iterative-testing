const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync } = require("node:child_process");

test("package name present", () => {
  const pkg = require("../package.json");
  assert.equal(pkg.name, "mit-demo-webapi");
});

test("server module loads", () => {
  const src = require("fs").readFileSync(require("path").join(__dirname, "..", "server.js"), "utf8");
  assert.match(src, /\/api\/health/);
  assert.match(src, /\/api\/orders/);
});
