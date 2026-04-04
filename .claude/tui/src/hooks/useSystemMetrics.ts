import { useState, useEffect } from "react";
import * as os from "os";
import type { SystemMetrics } from "../types/index.js";

/**
 * Hook for real system metrics (CPU/memory)
 * Uses Node.js os module for actual system data
 */
export function useSystemMetrics(pollInterval = 2000): SystemMetrics {
  const [metrics, setMetrics] = useState<SystemMetrics>(() =>
    getSystemMetrics(),
  );

  useEffect(() => {
    const timer = setInterval(() => {
      setMetrics(getSystemMetrics());
    }, pollInterval);

    return () => clearInterval(timer);
  }, [pollInterval]);

  return metrics;
}

function getSystemMetrics(): SystemMetrics {
  // Memory
  const totalMemory = os.totalmem();
  const freeMemory = os.freemem();
  const usedMemory = totalMemory - freeMemory;

  const memoryTotalGB = totalMemory / (1024 * 1024 * 1024);
  const memoryUsedGB = usedMemory / (1024 * 1024 * 1024);

  // CPU - calculate average load percentage
  const cpus = os.cpus();
  let totalIdle = 0;
  let totalTick = 0;

  for (const cpu of cpus) {
    for (const type in cpu.times) {
      totalTick += cpu.times[type as keyof typeof cpu.times];
    }
    totalIdle += cpu.times.idle;
  }

  const cpuPercent = 100 - Math.round((totalIdle / totalTick) * 100);

  // Uptime
  const uptime = os.uptime();

  return {
    memoryUsedGB: Math.round(memoryUsedGB * 10) / 10,
    memoryTotalGB: Math.round(memoryTotalGB * 10) / 10,
    cpuPercent: Math.max(0, Math.min(100, cpuPercent)),
    uptime,
  };
}
