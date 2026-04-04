import type { CostMetrics } from "../types/index.js";

/**
 * Mock cost data for demo/development mode
 */

export const MOCK_COSTS: CostMetrics = {
  today: 12.47,
  todayDelta: 3.2,
  sessions: 8,
  sessionsDelta: 2,
  sevenDay: 87.32,
  sevenDayDelta: 12.5,
  thirtyDay: 312.89,
  thirtyDayDelta: 45.0,
};

export function getMockCosts(): CostMetrics {
  return MOCK_COSTS;
}

/**
 * Generate randomized cost data for testing
 */
export function generateRandomCosts(): CostMetrics {
  const today = Math.random() * 10;
  const sessions = Math.floor(Math.random() * 20) + 1;
  const sevenDay = today * (5 + Math.random() * 3);
  const thirtyDay = sevenDay * (3 + Math.random() * 2);

  return {
    today: Math.round(today * 100) / 100,
    todayDelta: Math.round((Math.random() - 0.3) * 5 * 100) / 100,
    sessions,
    sessionsDelta: Math.floor((Math.random() - 0.3) * 5),
    sevenDay: Math.round(sevenDay * 100) / 100,
    sevenDayDelta: Math.round((Math.random() - 0.5) * 10 * 100) / 100,
    thirtyDay: Math.round(thirtyDay * 100) / 100,
    thirtyDayDelta: Math.round((Math.random() - 0.3) * 30 * 100) / 100,
  };
}
