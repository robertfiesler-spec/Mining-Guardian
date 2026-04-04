import { describe, it, expect, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, appendFileSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { EventEmitter } from "events";
import { LogTailer, LogTailerManager } from "../../src/log-tailer.js";

let tempDir: string;
const cleanupFns: Array<() => void> = [];

afterEach(async () => {
  for (const fn of cleanupFns) {
    fn();
  }
  cleanupFns.length = 0;

  // Allow pending stream operations to complete before deleting temp files
  await new Promise((resolve) => setTimeout(resolve, 50));

  if (tempDir) {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

function setupTempDir(): string {
  tempDir = mkdtempSync(join(tmpdir(), "log-tailer-test-"));
  return tempDir;
}

function waitForEvent(
  emitter: EventEmitter,
  event: string,
  timeout = 3000,
): Promise<unknown[]> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () =>
        reject(
          new Error(`Timeout waiting for '${event}' event after ${timeout}ms`),
        ),
      timeout,
    );
    emitter.once(event, (...args: unknown[]) => {
      clearTimeout(timer);
      resolve(args);
    });
  });
}

describe("LogTailer", () => {
  it("emits error event when file does not exist", async () => {
    const dir = setupTempDir();
    const tailer = new LogTailer({
      filePath: join(dir, "nonexistent.log"),
      instanceId: "test-1",
      pollInterval: 50,
    });
    cleanupFns.push(() => tailer.stop());

    const errorPromise = waitForEvent(tailer, "error");
    await tailer.start();

    const [instanceId, error] = await errorPromise;
    expect(instanceId).toBe("test-1");
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toContain("Log file not found");

    tailer.stop();
  });

  it("emits lines event when file has content", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "test.log");
    writeFileSync(logFile, "line one\nline two\n");

    const tailer = new LogTailer({
      filePath: logFile,
      instanceId: "test-2",
      pollInterval: 50,
    });
    cleanupFns.push(() => tailer.stop());

    const linesPromise = waitForEvent(tailer, "lines");
    await tailer.start();

    const [instanceId, lines] = await linesPromise;
    expect(instanceId).toBe("test-2");
    expect(lines).toContain("line one");
    expect(lines).toContain("line two");

    tailer.stop();
  });

  it("strips ANSI escape codes from lines when stripAnsi is true", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "ansi.log");
    // Write ANSI-encoded content: red "hello" and reset
    writeFileSync(logFile, "\u001b[31mhello\u001b[0m world\n");

    const tailer = new LogTailer({
      filePath: logFile,
      instanceId: "test-ansi",
      pollInterval: 50,
      stripAnsi: true,
    });
    cleanupFns.push(() => tailer.stop());

    const linesPromise = waitForEvent(tailer, "lines");
    await tailer.start();

    const [, lines] = await linesPromise;
    const linesArray = lines as string[];
    expect(linesArray).toHaveLength(1);
    expect(linesArray[0]).toBe("hello world");
    // Verify no ANSI codes remain
    expect(linesArray[0]).not.toContain("\u001b");

    tailer.stop();
  });

  it("preserves ANSI codes when stripAnsi is false", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "ansi-preserve.log");
    writeFileSync(logFile, "\u001b[31mhello\u001b[0m world\n");

    const tailer = new LogTailer({
      filePath: logFile,
      instanceId: "test-preserve",
      pollInterval: 50,
      stripAnsi: false,
    });
    cleanupFns.push(() => tailer.stop());

    const linesPromise = waitForEvent(tailer, "lines");
    await tailer.start();

    const [, lines] = await linesPromise;
    const linesArray = lines as string[];
    expect(linesArray).toHaveLength(1);
    expect(linesArray[0]).toContain("\u001b[31m");
    expect(linesArray[0]).toContain("\u001b[0m");

    tailer.stop();
  });

  it("filters empty lines", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "empty-lines.log");
    writeFileSync(logFile, "first\n\n\nsecond\n  \n");

    const tailer = new LogTailer({
      filePath: logFile,
      instanceId: "test-empty",
      pollInterval: 50,
    });
    cleanupFns.push(() => tailer.stop());

    const linesPromise = waitForEvent(tailer, "lines");
    await tailer.start();

    const [, lines] = await linesPromise;
    const linesArray = lines as string[];
    expect(linesArray).toEqual(["first", "second"]);

    tailer.stop();
  });

  it("detects new content appended to file", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "append.log");
    writeFileSync(logFile, "initial line\n");

    const tailer = new LogTailer({
      filePath: logFile,
      instanceId: "test-append",
      pollInterval: 50,
    });
    cleanupFns.push(() => tailer.stop());

    // Wait for initial lines
    const firstPromise = waitForEvent(tailer, "lines");
    await tailer.start();
    await firstPromise;

    // Append new content and wait for it
    const secondPromise = waitForEvent(tailer, "lines");
    appendFileSync(logFile, "appended line\n");

    const [, newLines] = await secondPromise;
    const linesArray = newLines as string[];
    expect(linesArray).toContain("appended line");

    tailer.stop();
  });

  it("stop() stops polling", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "stop.log");
    writeFileSync(logFile, "data\n");

    const tailer = new LogTailer({
      filePath: logFile,
      instanceId: "test-stop",
      pollInterval: 50,
    });

    // Wait for the initial lines event so we know the first poll has completed
    const initialPromise = waitForEvent(tailer, "lines");
    await tailer.start();
    await initialPromise;

    tailer.stop();

    // After stopping, appending should not emit lines
    let emitted = false;
    tailer.on("lines", () => {
      emitted = true;
    });

    appendFileSync(logFile, "should not emit\n");

    // Wait enough time for a poll cycle
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(emitted).toBe(false);
  });
});

describe("LogTailerManager", () => {
  function createManager(dir: string): LogTailerManager {
    const manager = new LogTailerManager(dir);
    // Prevent unhandled error events from crashing the test process.
    // Late stream errors can fire after stopAll/removeAllListeners.
    manager.on("error", () => {});
    cleanupFns.push(() => manager.stopAll());
    return manager;
  }

  it("addTailer creates and starts a tailer", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "managed.log");
    writeFileSync(logFile, "managed content\n");

    const manager = createManager(dir);

    const linesPromise = waitForEvent(manager, "lines");
    manager.addTailer("instance-1", logFile);

    const [instanceId, lines] = await linesPromise;
    expect(instanceId).toBe("instance-1");
    expect(lines).toContain("managed content");
    expect(manager.getActiveTailers()).toContain("instance-1");

    manager.stopAll();
  });

  it("removeTailer stops and removes a tailer", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "remove.log");
    writeFileSync(logFile, "content\n");

    const manager = createManager(dir);

    const linesPromise = waitForEvent(manager, "lines");
    manager.addTailer("instance-2", logFile);
    await linesPromise;

    expect(manager.getActiveTailers()).toContain("instance-2");

    manager.removeTailer("instance-2");
    expect(manager.getActiveTailers()).not.toContain("instance-2");
  });

  it("stopAll stops all tailers", async () => {
    const dir = setupTempDir();
    const logFile1 = join(dir, "file1.log");
    const logFile2 = join(dir, "file2.log");
    writeFileSync(logFile1, "content1\n");
    writeFileSync(logFile2, "content2\n");

    const manager = createManager(dir);
    manager.addTailer("inst-a", logFile1);
    manager.addTailer("inst-b", logFile2);

    // Wait a tick for tailers to start
    await new Promise((resolve) => setTimeout(resolve, 100));

    expect(manager.getActiveTailers()).toHaveLength(2);

    manager.stopAll();
    expect(manager.getActiveTailers()).toHaveLength(0);
  });

  it("getActiveTailers returns active instance IDs", () => {
    const dir = setupTempDir();
    const logFile = join(dir, "active.log");
    writeFileSync(logFile, "content\n");

    const manager = createManager(dir);

    expect(manager.getActiveTailers()).toEqual([]);

    manager.addTailer("id-one", logFile);
    expect(manager.getActiveTailers()).toEqual(["id-one"]);

    manager.stopAll();
  });

  it("forwards lines events from child tailers", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "forward.log");
    writeFileSync(logFile, "forwarded content\n");

    const manager = createManager(dir);

    const linesPromise = waitForEvent(manager, "lines");
    manager.addTailer("fwd-inst", logFile);

    const [instanceId, lines] = await linesPromise;
    expect(instanceId).toBe("fwd-inst");
    expect(lines).toContain("forwarded content");

    manager.stopAll();
  });

  it("resolves relative paths against baseLogDir", async () => {
    const dir = setupTempDir();
    const logFile = join(dir, "relative.log");
    writeFileSync(logFile, "relative content\n");

    const manager = createManager(dir);

    const linesPromise = waitForEvent(manager, "lines");
    manager.addTailer("rel-inst", "relative.log");

    const [instanceId, lines] = await linesPromise;
    expect(instanceId).toBe("rel-inst");
    expect(lines).toContain("relative content");

    manager.stopAll();
  });
});
