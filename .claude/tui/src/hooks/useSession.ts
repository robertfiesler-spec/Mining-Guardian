import { useState, useEffect, useCallback } from "react";
import { readFileSync, watchFile, unwatchFile, existsSync } from "fs";
import { resolve } from "path";
import { SESSION_FILE } from "../constants.js";

export interface SessionState {
  version: string;
  created_at: string;
  updated_at: string;
  status: "running" | "paused" | "complete" | "crashed";
  plan: {
    path: string;
    name: string;
    branch: string;
  };
  progress: {
    total_stories: number;
    completed: number;
    current_story: string | null;
    current_iteration: number;
  };
  git: {
    branch: string;
    head_commit: string;
    modified_files: string[];
  };
  execution: {
    mode: "autonomous" | "attended";
    pid: number;
    start_time: string;
  };
  activity_log: Array<{
    timestamp: string;
    type:
      | "story_started"
      | "story_completed"
      | "error"
      | "pause"
      | "resume"
      | "complete";
    story: string;
    message: string;
  }>;
}

export interface SessionError {
  message: string;
  code: "FILE_NOT_FOUND" | "PARSE_ERROR" | "READ_ERROR";
  details?: string;
}

export interface UseSessionResult {
  session: SessionState | null;
  error: SessionError | null;
  isLoading: boolean;
}

/**
 * Hook to load and watch session state file
 * Automatically updates when the file changes
 * Returns session state, error info, and loading status
 */
export function useSession(): SessionState | null {
  const result = useSessionWithError();
  return result.session;
}

/**
 * Extended hook that provides error state for error handling
 */
export function useSessionWithError(): UseSessionResult {
  const [session, setSession] = useState<SessionState | null>(null);
  const [error, setError] = useState<SessionError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadSession = useCallback(() => {
    const sessionPath = resolve(process.cwd(), SESSION_FILE);

    try {
      if (!existsSync(sessionPath)) {
        setSession(null);
        setError(null); // No error, just no session yet
        setIsLoading(false);
        return;
      }

      const data = readFileSync(sessionPath, "utf-8");

      // Handle empty file
      if (!data.trim()) {
        setSession(null);
        setError({
          message: "Session file is empty",
          code: "PARSE_ERROR",
          details: "The session file exists but contains no data",
        });
        setIsLoading(false);
        return;
      }

      const parsed = JSON.parse(data);

      // Basic validation
      if (!parsed.version || !parsed.status) {
        setSession(null);
        setError({
          message: "Invalid session format",
          code: "PARSE_ERROR",
          details: "Session file is missing required fields (version, status)",
        });
        setIsLoading(false);
        return;
      }

      setSession(parsed);
      setError(null);
      setIsLoading(false);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);

      if (errorMessage.includes("JSON")) {
        setError({
          message: "Failed to parse session file",
          code: "PARSE_ERROR",
          details: errorMessage,
        });
      } else {
        setError({
          message: "Failed to read session file",
          code: "READ_ERROR",
          details: errorMessage,
        });
      }

      setSession(null);
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const sessionPath = resolve(process.cwd(), SESSION_FILE);

    // Initial load
    loadSession();

    // Watch for changes
    watchFile(sessionPath, { interval: 500 }, () => {
      loadSession();
    });

    // Cleanup
    return () => {
      unwatchFile(sessionPath);
    };
  }, [loadSession]);

  return { session, error, isLoading };
}
