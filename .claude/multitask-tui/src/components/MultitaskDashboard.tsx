import React, { useState, useEffect } from 'react';
import { Box, Text, useInput, useApp } from 'ink';
import Spinner from 'ink-spinner';
import * as fs from 'fs';
import * as path from 'path';

interface Instance {
  instance_num: number;
  worktree: string;
  branch: string;
  plan: string;
  pid: number;
  status: string;
  started: string;
  log_file: string;
}

interface Session {
  session_id: string;
  started: string;
  tui_enabled: boolean;
  max_iterations: number;
  instances: Instance[];
  tui_pid?: string;
}

const SESSION_FILE = '.claude/state/multitask-session.json';
const REFRESH_INTERVAL = 2000; // 2 seconds

export function MultitaskDashboard() {
  const { exit } = useApp();
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedAction, setSelectedAction] = useState<string | null>(null);

  // Load session data
  useEffect(() => {
    const loadSession = () => {
      try {
        if (!fs.existsSync(SESSION_FILE)) {
          setError('No active multitask session found');
          return;
        }

        const data = fs.readFileSync(SESSION_FILE, 'utf-8');
        const sessionData = JSON.parse(data) as Session;
        setSession(sessionData);
        setError(null);
      } catch (err) {
        setError(`Failed to load session: ${err}`);
      }
    };

    // Initial load
    loadSession();

    // Refresh every 2 seconds
    const interval = setInterval(loadSession, REFRESH_INTERVAL);

    return () => clearInterval(interval);
  }, []);

  // Handle keyboard input
  useInput((input, key) => {
    if (input === 'q' || key.escape) {
      exit();
    } else if (input === 's') {
      setSelectedAction('stop');
      // In real implementation, would call stop script
      setTimeout(() => setSelectedAction(null), 2000);
    } else if (input === 'p') {
      setSelectedAction('pause');
      setTimeout(() => setSelectedAction(null), 2000);
    } else if (input === 'r') {
      setSelectedAction('resume');
      setTimeout(() => setSelectedAction(null), 2000);
    } else if (input === 'c') {
      setSelectedAction('cleanup');
      setTimeout(() => setSelectedAction(null), 2000);
    }
  });

  // Check if all instances are complete
  const allComplete = session?.instances.every(
    (inst) => inst.status === 'completed' || inst.status === 'stopped'
  ) ?? false;

  // Calculate progress for each instance
  const getInstanceProgress = (instance: Instance): string => {
    try {
      const planPath = path.join(instance.worktree, instance.plan);
      if (!fs.existsSync(planPath)) {
        return '0/0';
      }

      const planData = JSON.parse(fs.readFileSync(planPath, 'utf-8'));
      const total = planData.stories?.length || 0;
      const completed =
        planData.stories?.filter((s: any) => s.passes === true).length || 0;

      return `${completed}/${total}`;
    } catch {
      return 'N/A';
    }
  };

  // Get status color
  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'running':
        return 'green';
      case 'completed':
        return 'blue';
      case 'stopped':
        return 'red';
      case 'paused':
        return 'yellow';
      default:
        return 'white';
    }
  };

  if (error) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text color="red">Error: {error}</Text>
        <Text dimColor>Press 'q' to exit</Text>
      </Box>
    );
  }

  if (!session) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text>
          <Spinner type="dots" /> Loading session...
        </Text>
      </Box>
    );
  }

  const runningCount = session.instances.filter(
    (i) => i.status === 'running'
  ).length;

  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <Box borderStyle="round" borderColor="cyan" paddingX={2} paddingY={1}>
        <Box flexDirection="column" width="100%">
          <Box justifyContent="space-between">
            <Text bold>Multitask Session</Text>
            <Text>
              {runningCount} instance{runningCount !== 1 ? 's' : ''} running
            </Text>
          </Box>
          <Text dimColor>Session: {session.session_id}</Text>
        </Box>
      </Box>

      {/* Instances */}
      <Box flexDirection="column" marginTop={1}>
        {session.instances.map((instance) => {
          const progress = getInstanceProgress(instance);
          const statusColor = getStatusColor(instance.status);
          const isRunning = instance.status === 'running';

          return (
            <Box
              key={instance.instance_num}
              borderStyle="round"
              borderColor={statusColor}
              paddingX={2}
              paddingY={1}
              marginBottom={1}
              flexDirection="column"
            >
              <Text bold>
                Instance {instance.instance_num}: {instance.branch}
              </Text>
              <Text dimColor>Worktree: {instance.worktree}</Text>
              <Box marginTop={1}>
                <Text>
                  Status: <Text color={statusColor}>{instance.status}</Text>
                  {isRunning && <Spinner type="dots" />}
                </Text>
              </Box>
              <Text>Progress: {progress}</Text>
              <Text dimColor>PID: {instance.pid}</Text>
            </Box>
          );
        })}
      </Box>

      {/* Action feedback */}
      {selectedAction && (
        <Box marginTop={1}>
          <Text color="yellow">
            Action: {selectedAction.toUpperCase()} (not yet implemented)
          </Text>
        </Box>
      )}

      {/* Controls */}
      <Box borderStyle="single" borderColor="gray" paddingX={2} marginTop={1}>
        <Text>
          [s] stop all · [p] pause all · [r] resume all · [c] cleanup · [q]
          quit
        </Text>
      </Box>

      {/* Completion message */}
      {allComplete && (
        <Box marginTop={1}>
          <Text color="green" bold>
            ✓ All instances completed! Press 'q' to exit.
          </Text>
        </Box>
      )}
    </Box>
  );
}
