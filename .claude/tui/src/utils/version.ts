import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

/**
 * Get the TUI version from package.json
 * This ensures the version displayed matches the actual package version
 */
export function getVersion(): string {
  try {
    // Get the directory of this file, then navigate to package.json
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = dirname(__filename);
    const packagePath = resolve(__dirname, "../../package.json");

    const packageJson = JSON.parse(readFileSync(packagePath, "utf-8"));
    return packageJson.version || "0.0.0";
  } catch {
    // Fallback if we can't read package.json
    return "0.0.0";
  }
}

/**
 * Cached version to avoid reading file multiple times
 */
let cachedVersion: string | null = null;

export function getCachedVersion(): string {
  if (!cachedVersion) {
    cachedVersion = getVersion();
  }
  return cachedVersion;
}
