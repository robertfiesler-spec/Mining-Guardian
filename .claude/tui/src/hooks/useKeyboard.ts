import { useEffect } from "react";
import { useInput } from "ink";
import { writeFileSync, unlinkSync, existsSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { PAUSE_FILE, QUIT_FILE, STATE_DIR } from "../constants.js";

export interface KeyboardHandlers {
  /** Whether the keyboard handler is active. Defaults to true. */
  isActive?: boolean;
  onPause?: () => void;
  onResume?: () => void;
  onQuit?: () => void;
  onLogs?: () => void;
  onStatus?: () => void;
  onHelp?: () => void;
  onOrchestrator?: () => void;
  onRefresh?: () => void;
}

/**
 * Hook to handle keyboard input for TUI controls
 * - p: Pause the loop (creates semaphore file)
 * - r: Resume the loop (removes semaphore file)
 * - q: Quit gracefully (creates quit semaphore)
 *
 * @param handlers - Keyboard event handlers and options
 * @param handlers.isActive - When false, all keyboard input is ignored.
 *   Use this to disable handling during mode selection or other screens
 *   that have their own input handlers.
 */
export function useKeyboard(handlers: KeyboardHandlers = {}) {
  const { isActive = true } = handlers;
  const stateDir = resolve(process.cwd(), STATE_DIR);
  const pausePath = resolve(process.cwd(), PAUSE_FILE);
  const quitPath = resolve(process.cwd(), QUIT_FILE);

  // Ensure state directory exists
  const ensureStateDir = () => {
    if (!existsSync(stateDir)) {
      mkdirSync(stateDir, { recursive: true });
    }
  };

  useInput((input, key) => {
    // Skip all handling when inactive (e.g., mode select screen has its own handlers)
    if (!isActive) {
      return;
    }

    // Ignore Ctrl+C (handled by Ink's default behavior)
    if (key.ctrl && input === "c") {
      return;
    }

    switch (input.toLowerCase()) {
      case "p":
        // Pause: create semaphore file
        try {
          ensureStateDir();
          writeFileSync(pausePath, new Date().toISOString(), "utf-8");
          handlers.onPause?.();
        } catch {
          // Silently fail - console.error interferes with Ink rendering
        }
        break;

      case "r":
        // Resume: remove semaphore file
        try {
          if (existsSync(pausePath)) {
            unlinkSync(pausePath);
            handlers.onResume?.();
          }
        } catch {
          // Silently fail - console.error interferes with Ink rendering
        }
        break;

      case "q":
        // Quit: create quit semaphore file
        try {
          ensureStateDir();
          writeFileSync(quitPath, new Date().toISOString(), "utf-8");
          handlers.onQuit?.();
        } catch {
          // Silently fail - console.error interferes with Ink rendering
        }
        break;

      case "l":
        // Open log viewer
        handlers.onLogs?.();
        break;

      case "s":
        // Open status viewer
        handlers.onStatus?.();
        break;

      case "h":
        // Open help modal
        handlers.onHelp?.();
        break;

      case "o":
        // Toggle orchestrator view
        handlers.onOrchestrator?.();
        break;
    }
  });

  // Cleanup on unmount - only clean up pause file
  // NOTE: Do NOT delete quit file here. The quit file must persist until
  // loop.sh reads it and handles the graceful exit. loop.sh deletes the
  // quit file after processing. Deleting it here causes a race condition
  // where the TUI exits before loop.sh checks for the quit signal.
  useEffect(() => {
    return () => {
      // Only clean up pause file - prevents loop.sh from hanging if TUI crashes while paused
      try {
        if (existsSync(pausePath)) unlinkSync(pausePath);
      } catch (error) {
        // Ignore cleanup errors
      }
    };
  }, [pausePath]);
}
