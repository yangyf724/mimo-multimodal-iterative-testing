const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = process.env.PORT || 3456;

function send(res, code, body, type = "application/json") {
  res.writeHead(code, { "content-type": type });
  res.end(body);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === "/api/health") {
    return send(res, 200, JSON.stringify({ ok: true, service: "mit-demo-webapi" }));
  }
  if (url.pathname === "/api/orders" && req.method === "POST") {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try {
        const body = JSON.parse(raw || "{}");
        if (!body.item || typeof body.qty !== "number") {
          return send(res, 400, JSON.stringify({ error: "invalid order" }));
        }
        return send(res, 201, JSON.stringify({ id: "ord_1", ...body }));
      } catch {
        return send(res, 400, JSON.stringify({ error: "bad json" }));
      }
    });
    return;
  }
  const file = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\//, "");
  const fp = path.join(__dirname, "public", file);
  if (fp.startsWith(path.join(__dirname, "public")) && fs.existsSync(fp) && fs.statSync(fp).isFile()) {
    const ext = path.extname(fp);
    const type = ext === ".html" ? "text/html" : ext === ".css" ? "text/css" : "text/plain";
    return send(res, 200, fs.readFileSync(fp), type);
  }
  send(res, 404, JSON.stringify({ error: "not found" }));
});

server.listen(PORT, () => {
  console.log(`mit-demo-webapi listening on ${PORT}`);
});
// fix: planted P0 addressed (DoD demo)
