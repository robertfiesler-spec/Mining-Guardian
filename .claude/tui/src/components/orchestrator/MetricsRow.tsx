import React from "react";
import { Box } from "ink";
import { MetricCard } from "./MetricCard.js";
import { SectionHeader } from "../primitives/SectionHeader.js";
import { formatCurrency } from "../../utils/format.js";
import type { CostMetrics } from "../../types/index.js";

interface MetricsRowProps {
  costs: CostMetrics;
}

/**
 * Row of 3 metric cards showing costs
 */
export function MetricsRow({ costs }: MetricsRowProps) {
  return (
    <Box flexDirection="column">
      <SectionHeader title="COST METRICS" />
      <Box flexDirection="row" marginTop={1}>
        <MetricCard
          title="Today"
          value={formatCurrency(costs.today)}
          delta={costs.todayDelta}
          deltaPrefix="$"
        />
        <MetricCard
          title="Last 7 Days"
          value={formatCurrency(costs.sevenDay)}
          delta={costs.sevenDayDelta}
          deltaPrefix="$"
        />
        <MetricCard
          title="Last 30 Days"
          value={formatCurrency(costs.thirtyDay)}
          delta={costs.thirtyDayDelta}
          deltaPrefix="$"
        />
      </Box>
    </Box>
  );
}
