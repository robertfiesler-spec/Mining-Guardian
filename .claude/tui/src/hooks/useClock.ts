import { useState, useEffect } from "react";
import { formatTime } from "../utils/format.js";

interface ClockState {
  time: string;
  date: Date;
}

/**
 * Hook for real-time clock display
 * Updates every second with formatted time
 */
export function useClock(updateInterval = 1000): ClockState {
  const [clockState, setClockState] = useState<ClockState>(() => {
    const now = new Date();
    return {
      time: formatTime(now),
      date: now,
    };
  });

  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      setClockState({
        time: formatTime(now),
        date: now,
      });
    }, updateInterval);

    return () => clearInterval(timer);
  }, [updateInterval]);

  return clockState;
}

/**
 * Simple time string hook
 */
export function useTimeString(): string {
  const { time } = useClock();
  return time;
}
