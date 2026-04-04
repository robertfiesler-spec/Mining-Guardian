import * as fs from 'node:fs';
import * as path from 'node:path';
import { EventEmitter } from 'node:events';

interface LogTailerOptions {
  /**
   * Path to the log file to tail
   */
  filePath: string;

  /**
   * Instance ID for this log file
   */
  instanceId: string;

  /**
   * Number of lines to read initially (default: 100)
   */
  initialLines?: number;

  /**
   * Poll interval in milliseconds (default: 500)
   */
  pollInterval?: number;

  /**
   * Whether to strip ANSI escape codes (default: true)
   */
  stripAnsi?: boolean;
}

interface LogTailerEvents {
  lines: (instanceId: string, lines: string[]) => void;
  error: (instanceId: string, error: Error) => void;
}

declare interface LogTailer {
  on<U extends keyof LogTailerEvents>(event: U, listener: LogTailerEvents[U]): this;
  emit<U extends keyof LogTailerEvents>(event: U, ...args: Parameters<LogTailerEvents[U]>): boolean;
}

/**
 * LogTailer watches a log file and emits new lines as they are written.
 * It strips ANSI escape codes by default and handles file rotation gracefully.
 */
class LogTailer extends EventEmitter {
  private filePath: string;
  private instanceId: string;
  private pollInterval: number;
  private stripAnsi: boolean;
  private lastPosition: number = 0;
  private pollTimer?: NodeJS.Timeout;
  private isRunning: boolean = false;
  private lastSize: number = 0;

  constructor(options: LogTailerOptions) {
    super();
    this.filePath = options.filePath;
    this.instanceId = options.instanceId;
    this.pollInterval = options.pollInterval ?? 500;
    this.stripAnsi = options.stripAnsi ?? true;
  }

  /**
   * Return the absolute file path currently being tailed.
   */
  getFilePath(): string {
    return this.filePath;
  }

  /**
   * Whether the tailer is currently running.
   */
  isStarted(): boolean {
    return this.isRunning;
  }

  /**
   * Start tailing the log file
   */
  async start(): Promise<void> {
    if (this.isRunning) {
      return;
    }

    this.isRunning = true;

    // Check if file exists, if not wait for it
    if (!fs.existsSync(this.filePath)) {
      this.emit('error', this.instanceId, new Error(`Log file not found: ${this.filePath}`));
      // Still start polling in case the file is created later
    }

    // Start polling
    this.poll();
  }

  /**
   * Stop tailing the log file
   */
  stop(): void {
    this.isRunning = false;
    if (this.pollTimer) {
      clearTimeout(this.pollTimer);
      this.pollTimer = undefined;
    }
  }

  /**
   * Poll the log file for new content
   */
  private poll(): void {
    if (!this.isRunning) {
      return;
    }

    this.checkForNewLines()
      .catch((error) => {
        this.emit('error', this.instanceId, error as Error);
      })
      .finally(() => {
        if (this.isRunning) {
          this.pollTimer = setTimeout(() => this.poll(), this.pollInterval);
        }
      });
  }

  /**
   * Check for new lines in the log file
   */
  private async checkForNewLines(): Promise<void> {
    // Check if file exists
    if (!fs.existsSync(this.filePath)) {
      return;
    }

    let stats: fs.Stats;
    try {
      stats = await fs.promises.stat(this.filePath);
    } catch (error) {
      // File can disappear between existsSync() and stat() (rotation, cleanup, etc.)
      if (error instanceof Error && 'code' in error && (error as NodeJS.ErrnoException).code === 'ENOENT') {
        return;
      }
      throw error;
    }

    const currentSize = stats.size;

    // File was truncated or rotated
    if (currentSize < this.lastSize) {
      this.lastPosition = 0;
    }

    this.lastSize = currentSize;

    // No new content
    if (currentSize <= this.lastPosition) {
      return;
    }

    // Read new content.
    //
    // IMPORTANT: We must await stream completion before returning, otherwise the
    // polling loop can overlap reads and emit duplicate lines.
    const stream = fs.createReadStream(this.filePath, {
      start: this.lastPosition,
      end: currentSize - 1,
      encoding: 'utf8',
    });

    const buffer = await new Promise<string>((resolve, reject) => {
      let data = '';

      stream.on('data', (chunk: string | Buffer) => {
        data += chunk.toString();
      });

      stream.once('end', () => resolve(data));
      stream.once('error', reject);
    });

    this.lastPosition = currentSize;

    // Split into lines
    const lines = buffer.split('\n');

    // Filter out empty lines
    const nonEmptyLines = lines.filter((line) => line.trim().length > 0);

    if (!this.isRunning) {
      return;
    }

    if (nonEmptyLines.length > 0) {
      // Strip ANSI codes if requested
      const processedLines = this.stripAnsi
        ? nonEmptyLines.map((line) => this.removeAnsiCodes(line))
        : nonEmptyLines;

      this.emit('lines', this.instanceId, processedLines);
    }
  }

  /**
   * Remove ANSI escape codes from a string
   */
  private removeAnsiCodes(str: string): string {
    // ANSI escape code regex pattern
    // Matches ESC[...m (SGR), ESC[...J (clear), ESC[...K (erase line), etc.
    const ansiPattern =
      // eslint-disable-next-line no-control-regex
      /\u001b\[[0-9;]*[a-zA-Z]|\u001b\][0-9;]*;[^\u0007]*\u0007|\u001b\][^\u0007]*\u0007/g;

    return str.replace(ansiPattern, '');
  }
}

/**
 * LogTailerManager manages multiple log tailers for different instances
 */
export class LogTailerManager extends EventEmitter {
  private tailers: Map<string, LogTailer> = new Map();
  private baseLogDir: string;

  constructor(baseLogDir: string) {
    super();
    this.baseLogDir = baseLogDir;
  }

  /**
   * Add a log file to tail
   */
  addTailer(instanceId: string, logFilePath: string): void {
    // Resolve absolute path
    const absolutePath = path.isAbsolute(logFilePath)
      ? logFilePath
      : path.join(this.baseLogDir, logFilePath);

    const existingTailer = this.tailers.get(instanceId);
    if (existingTailer) {
      // If we're already tailing this exact file, keep the existing tailer so we
      // don't reset lastPosition and re-broadcast the entire log on every state update.
      if (existingTailer.getFilePath() === absolutePath) {
        if (!existingTailer.isStarted()) {
          existingTailer.start().catch((error) => {
            this.emit('error', instanceId, error as Error);
          });
        }
        return;
      }

      // Different file path for same instance ID (rotation / config change).
      this.removeTailer(instanceId);
    }

    const tailer = new LogTailer({
      filePath: absolutePath,
      instanceId,
      stripAnsi: true,
    });

    // Forward events
    tailer.on('lines', (id, lines) => {
      this.emit('lines', id, lines);
    });

    tailer.on('error', (id, error) => {
      this.emit('error', id, error);
    });

    this.tailers.set(instanceId, tailer);
    tailer.start().catch((error) => {
      this.emit('error', instanceId, error);
    });
  }

  /**
   * Remove a tailer by instance ID
   */
  removeTailer(instanceId: string): void {
    const tailer = this.tailers.get(instanceId);
    if (tailer) {
      tailer.stop();
      tailer.removeAllListeners();
      this.tailers.delete(instanceId);
    }
  }

  /**
   * Stop all tailers
   */
  stopAll(): void {
    for (const tailer of this.tailers.values()) {
      tailer.stop();
      tailer.removeAllListeners();
    }
    this.tailers.clear();
  }

  /**
   * Get list of active tailer instance IDs
   */
  getActiveTailers(): string[] {
    return Array.from(this.tailers.keys());
  }
}

export type { LogTailerOptions, LogTailerEvents };
export { LogTailer };
