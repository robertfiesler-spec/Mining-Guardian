import { describe, it, expect, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { request as httpRequest } from "http";
import { createHttpServer, startHttpServer } from "../../src/http-server.js";

import type { Server } from "http";

let tempDir: string;
let server: Server | undefined;

afterEach(async () => {
  if (server) {
    await new Promise<void>((resolve) => {
      server!.close(() => resolve());
    });
    server = undefined;
  }

  if (tempDir) {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

function setupTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), "http-server-test-"));
  return tempDir;
}

function getServerUrl(srv: Server): string {
  const address = srv.address();
  if (typeof address === "string") {
    return address;
  }
  return `http://localhost:${address!.port}`;
}

async function startServer(publicDir: string): Promise<Server> {
  server = createHttpServer({ port: 0, publicDir });
  return new Promise<Server>((resolve) => {
    server!.listen(0, () => resolve(server!));
  });
}

describe("createHttpServer", () => {
  it("serves index.html for root path /", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "index.html"), "<html><body>Hello</body></html>");

    const srv = await startServer(dir);
    const url = getServerUrl(srv);

    const response = await fetch(`${url}/`);
    expect(response.status).toBe(200);

    const body = await response.text();
    expect(body).toBe("<html><body>Hello</body></html>");
  });

  it("returns correct Content-Type for .html files", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "index.html"), "<html></html>");

    const srv = await startServer(dir);
    const url = getServerUrl(srv);

    const response = await fetch(`${url}/index.html`);
    expect(response.headers.get("content-type")).toBe("text/html");
  });

  it("returns correct Content-Type for .css files", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "style.css"), "body { color: red; }");

    const srv = await startServer(dir);
    const url = getServerUrl(srv);

    const response = await fetch(`${url}/style.css`);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("text/css");

    const body = await response.text();
    expect(body).toBe("body { color: red; }");
  });

  it("returns correct Content-Type for .js files", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "app.js"), 'console.log("hello");');

    const srv = await startServer(dir);
    const url = getServerUrl(srv);

    const response = await fetch(`${url}/app.js`);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/javascript");

    const body = await response.text();
    expect(body).toBe('console.log("hello");');
  });

  it("strips query strings from URL", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "index.html"), "query test");

    const srv = await startServer(dir);
    const url = getServerUrl(srv);

    const response = await fetch(`${url}/index.html?v=123&cache=bust`);
    expect(response.status).toBe(200);

    const body = await response.text();
    expect(body).toBe("query test");
  });

  it("returns 403 for path traversal attempts", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "index.html"), "safe");

    const srv = await startServer(dir);
    const address = srv.address();
    const port = typeof address === "string" ? 80 : address!.port;

    // Use raw HTTP request to send path traversal without browser/fetch normalization
    const response = await new Promise<{ status: number; body: string }>(
      (resolve) => {
        const req = httpRequest(
          {
            hostname: "localhost",
            port,
            path: "/..%2F..%2F..%2Fetc/passwd",
            method: "GET",
          },
          (res) => {
            let body = "";
            res.on("data", (chunk: Buffer) => {
              body += chunk.toString();
            });
            res.on("end", () => resolve({ status: res.statusCode || 0, body }));
          },
        );
        req.end();
      },
    );

    // The server should either return 403 (traversal detected) or 404 (file not found).
    // The key assertion: it must never serve content from outside publicDir.
    expect([403, 404]).toContain(response.status);
    expect(response.body).not.toContain("root:");
  });

  it("returns 404 for non-existent files", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "index.html"), "exists");

    const srv = await startServer(dir);
    const url = getServerUrl(srv);

    const response = await fetch(`${url}/nonexistent.html`);
    expect(response.status).toBe(404);

    const body = await response.text();
    expect(body).toBe("Not Found");
  });

  it("serves files from subdirectories", async () => {
    const dir = setupTempDir();
    mkdirSync(join(dir, "js"));
    writeFileSync(join(dir, "js", "bundle.js"), "var x = 1;");

    const srv = await startServer(dir);
    const url = getServerUrl(srv);

    const response = await fetch(`${url}/js/bundle.js`);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/javascript");

    const body = await response.text();
    expect(body).toBe("var x = 1;");
  });
});

describe("startHttpServer", () => {
  it("resolves with a listening server", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "index.html"), "<html></html>");

    server = await startHttpServer({ port: 0, publicDir: dir });

    expect(server).toBeDefined();
    expect(server.listening).toBe(true);

    const address = server.address();
    expect(address).not.toBeNull();
    expect(typeof address).toBe("object");
    if (typeof address === "object" && address !== null) {
      expect(address.port).toBeGreaterThan(0);
    }
  });

  it("serves content after starting", async () => {
    const dir = setupTempDir();
    writeFileSync(join(dir, "index.html"), "started");

    server = await startHttpServer({ port: 0, publicDir: dir });
    const url = getServerUrl(server);

    const response = await fetch(`${url}/`);
    expect(response.status).toBe(200);

    const body = await response.text();
    expect(body).toBe("started");
  });
});
