/**
 * Integration test: full pipeline from file changes through WebSocket messages.
 *
 * Creates a temp directory structure mimicking the project layout,
 * wires up HTTP server + WebSocket + StateManager + LogTailerManager,
 * writes state files, and verifies clients receive the correct WS messages.
 */
import { describe, it, expect, afterEach } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import WebSocket from "ws";
import { createHttpServer } from "../../src/http-server.js";
import {
  createWebSocketServer,
  broadcast,
} from "../../src/websocket-server.js";
import { StateManager } from "../../src/state-manager.js";
import { LogTailerManager } from "../../src/log-tailer.js";
import { createRawOrchestratorJson } from "./factories.js";

import type { Server } from "http";
import type { WebSocketServer } from "ws";

let baseDir: string;
let httpServer: Server | undefined;
let wss: WebSocketServer | undefined;
let stateManager: StateManager | undefined;
let logManager: LogTailerManager | undefined;
let client: WebSocket | undefined;

function setupBaseDir(): string {
  baseDir = mkdtempSync(join(tmpdir(), "integration-test-"));
  mkdirSync(join(baseDir, ".claude", "state", "plans", "test-plan"), {
    recursive: true,
  });
  mkdirSync(join(baseDir, ".claude", "state", "logs"), { recursive: true });
  mkdirSync(join(baseDir, "docs", "plans"), { recursive: true });
  mkdirSync(join(baseDir, "public"), { recursive: true });
  writeFileSync(join(baseDir, "public", "index.html"), "<html></html>");
  return baseDir;
}

/**
 * Pre-create state files so fs.watch works (it requires existing files).
 * These are initially empty JSON so StateManager can start watching.
 */
function seedStateFiles(dir: string): void {
  writeFileSync(join(dir, ".claude", "state", "orchestrator.json"), "{}");
  writeFileSync(
    join(dir, ".claude", "state", "plans", "test-plan", "session.json"),
    "{}",
  );
  writeFileSync(join(dir, "docs", "plans", "test-plan.json"), "{}");
}

function collectMessages(
  ws: WebSocket,
  count: number,
  timeout = 10000,
): Promise<Record<string, unknown>[]> {
  return new Promise((resolve, reject) => {
    const messages: Record<string, unknown>[] = [];
    const timer = setTimeout(
      () =>
        reject(
          new Error(
            `Timeout: received ${messages.length}/${count} messages after ${timeout}ms`,
          ),
        ),
      timeout,
    );

    const onMessage = (data: Buffer) => {
      messages.push(JSON.parse(data.toString()));
      if (messages.length >= count) {
        clearTimeout(timer);
        ws.removeListener("message", onMessage);
        resolve(messages);
      }
    };

    ws.on("message", onMessage);
  });
}

afterEach(async () => {
  if (client && client.readyState !== WebSocket.CLOSED) {
    client.close();
    await new Promise<void>((resolve) => {
      client!.once("close", () => resolve());
      setTimeout(resolve, 500);
    });
  }
  client = undefined;

  stateManager?.stop();
  stateManager = undefined;

  logManager?.stopAll();
  logManager = undefined;

  if (wss) {
    wss.close();
    wss = undefined;
  }

  if (httpServer) {
    await new Promise<void>((resolve) => {
      httpServer!.close(() => resolve());
    });
    httpServer = undefined;
  }

  await new Promise((resolve) => setTimeout(resolve, 100));

  if (baseDir) {
    rmSync(baseDir, { recursive: true, force: true });
  }
});

describe("Integration: file → StateManager → WebSocket → client", () => {
  it("broadcasts orchestrator state update when orchestrator.json is modified", async () => {
    const dir = setupBaseDir();
    seedStateFiles(dir);

    // Start HTTP + WS server
    httpServer = createHttpServer({ port: 0, publicDir: join(dir, "public") });
    wss = createWebSocketServer({ httpServer, path: "/ws" });

    await new Promise<void>((resolve) => {
      httpServer!.listen(0, () => resolve());
    });

    const port = (httpServer.address() as { port: number }).port;

    // Initialize StateManager
    stateManager = new StateManager(dir, "test-plan");
    stateManager.on("error", () => {});

    // Wire state changes to WS broadcast (mimics server.ts)
    stateManager.on("orchestrator_update", (state) => {
      broadcast(wss!, { type: "state_update", orchestrator: state });
    });

    await stateManager.start();

    // Connect WS client - set up message collection before open
    client = new WebSocket(`ws://localhost:${port}/ws`);

    // The initial loadInitialState may broadcast empty/invalid state.
    // We need: 1 connection + at least 1 state_update from the file write.
    // Wait for connection first.
    await new Promise<void>((resolve) => {
      if (client!.readyState === WebSocket.OPEN) return resolve();
      client!.once("open", resolve);
    });

    // Drain any initial messages (connection + possibly initial state broadcasts)
    await new Promise((resolve) => setTimeout(resolve, 300));

    // Now set up a collector for the next state_update message
    const messagesPromise = collectMessages(client, 1, 5000);

    // Write valid orchestrator state - this triggers the fs.watch 'change' event
    const orchestratorData = createRawOrchestratorJson();
    writeFileSync(
      join(dir, ".claude", "state", "orchestrator.json"),
      JSON.stringify(orchestratorData, null, 2),
    );

    const messages = await messagesPromise;

    expect(messages[0].type).toBe("state_update");
    expect(messages[0].orchestrator).toBeDefined();
    const orchestrator = messages[0].orchestrator as Record<string, unknown>;
    expect(orchestrator.version).toBe("1.0");
  });

  it("broadcasts log lines when log file is appended", async () => {
    const dir = setupBaseDir();

    // Start HTTP + WS server
    httpServer = createHttpServer({ port: 0, publicDir: join(dir, "public") });
    wss = createWebSocketServer({ httpServer, path: "/ws" });

    await new Promise<void>((resolve) => {
      httpServer!.listen(0, () => resolve());
    });

    const port = (httpServer.address() as { port: number }).port;

    // Initialize LogTailerManager
    logManager = new LogTailerManager(dir);
    logManager.on("error", () => {});

    logManager.on("lines", (instanceId, lines) => {
      broadcast(wss!, {
        type: "log",
        instanceId,
        lines,
        timestamp: Date.now(),
      });
    });

    // Connect WS client first, before adding tailer,
    // so we don't miss the initial log broadcast
    client = new WebSocket(`ws://localhost:${port}/ws`);
    await new Promise<void>((resolve) => {
      if (client!.readyState === WebSocket.OPEN) return resolve();
      client!.once("open", resolve);
    });

    // Drain the connection message
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Now set up collector for log messages
    const messagesPromise = collectMessages(client, 1, 5000);

    // Create a log file and add tailer - this triggers the initial read
    const logFile = join(dir, ".claude", "state", "logs", "instance-1.log");
    writeFileSync(logFile, "[INFO] Server started\n");
    logManager.addTailer("instance-1", logFile);

    const messages = await messagesPromise;

    // Verify the log message
    expect(messages[0].type).toBe("log");
    expect(messages[0].instanceId).toBe("instance-1");
    const lines = messages[0].lines as string[];
    expect(lines.some((line) => line.includes("Server started"))).toBe(true);
  });
});
