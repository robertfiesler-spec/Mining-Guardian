import * as path from "node:path";
import { startHttpServer } from "./http-server.js";
import { createWebSocketServer, broadcast } from "./websocket-server.js";
import { StateManager } from "./state-manager.js";
import { LogTailerManager } from "./log-tailer.js";

const PORT = 8000;
const SCRIPT_DIR = path.dirname(new URL(import.meta.url).pathname);
const PUBLIC_DIR = path.join(SCRIPT_DIR, "..", "public");

async function main() {
  try {
    const httpServer = await startHttpServer({
      port: PORT,
      publicDir: PUBLIC_DIR,
    });

    // Initialize state manager
    const baseDir =
      process.env.WEB_VIEWER_BASE_DIR ?? path.resolve(process.cwd(), "../..");
    const planName = process.env.WEB_VIEWER_PLAN ?? "web-viewer";
    const stateManager = new StateManager(baseDir, planName);

    // Attach WebSocket server to HTTP server (with state snapshot for new clients)
    const wss = createWebSocketServer({
      httpServer,
      path: "/ws",
      getStateSnapshot: () => stateManager.getState(),
    });

    // Wire state changes to WebSocket broadcasts
    stateManager.on("orchestrator_update", (state) => {
      console.log("[Server] Broadcasting orchestrator update");
      broadcast(wss, {
        type: "state_update",
        orchestrator: state,
      });
    });

    stateManager.on("session_update", (state) => {
      console.log("[Server] Broadcasting session update");
      broadcast(wss, {
        type: "state_update",
        session: state,
      });
    });

    stateManager.on("plan_update", (plan) => {
      console.log("[Server] Broadcasting plan update");
      broadcast(wss, {
        type: "state_update",
        plan: plan,
      });
    });

    stateManager.on("plans_update", (plans) => {
      console.log(
        `[Server] Broadcasting plans update (${Object.keys(plans).length} plans)`,
      );
      broadcast(wss, {
        type: "state_update",
        plans,
      });
    });

    stateManager.on("pipeline_update", (pipelines) => {
      console.log(
        `[Server] Broadcasting pipeline update (${Object.keys(pipelines).length} pipelines)`,
      );
      broadcast(wss, {
        type: "state_update",
        pipelines,
      });
    });

    stateManager.on("error", (error) => {
      console.error("[Server] StateManager error:", error);
      broadcast(wss, {
        type: "error",
        message: error.message,
        timestamp: Date.now(),
      });
    });

    // Initialize log tailer manager
    const logTailerManager = new LogTailerManager(baseDir);

    // Wire log events to WebSocket broadcasts
    logTailerManager.on("lines", (instanceId, lines) => {
      broadcast(wss, {
        type: "log",
        instanceId,
        lines,
        timestamp: Date.now(),
      });
    });

    logTailerManager.on("error", (instanceId, error) => {
      console.error(`[Server] LogTailer error for ${instanceId}:`, error);
    });

    // Watch for orchestrator updates to add/remove log tailers
    // IMPORTANT: register before `stateManager.start()` so initial state can attach tailers.
    stateManager.on("orchestrator_update", (state) => {
      if (!state.instances) return;

      Object.entries(state.instances).forEach(([instanceId, instance]) => {
        // Check if instance has a log file
        if (!instance.logFile) return;

        const logPath = path.resolve(baseDir, instance.logFile);
        logTailerManager.addTailer(instanceId, logPath);
      });
    });

    // Start watching files
    await stateManager.start();

    console.log("Web viewer server started successfully");
    console.log(`HTTP: http://localhost:${PORT}`);
    console.log(`WebSocket: ws://localhost:${PORT}/ws`);
    console.log("State manager initialized and watching files");
    console.log("Log tailer manager initialized");

    // Graceful shutdown
    process.on("SIGINT", () => {
      console.log("\nShutting down gracefully...");
      stateManager.stop();
      logTailerManager.stopAll();
      httpServer.close(() => {
        console.log("Server closed");
        process.exit(0);
      });
    });
  } catch (error) {
    console.error("Failed to start server:", error);
    process.exit(1);
  }
}

main();
