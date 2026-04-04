import * as http from 'node:http';
import { WebSocketServer, WebSocket } from 'ws';

interface WebSocketServerOptions {
  httpServer: http.Server;
  path?: string;
  getStateSnapshot?: () => Promise<Record<string, unknown>>;
}

export function createWebSocketServer(options: WebSocketServerOptions): WebSocketServer {
  const { httpServer, path = '/ws', getStateSnapshot } = options;

  const wss = new WebSocketServer({
    server: httpServer,
    path,
  });

  wss.on('connection', (ws: WebSocket) => {
    console.log('WebSocket client connected');

    // Send initial connection confirmation
    ws.send(
      JSON.stringify({
        type: 'connection',
        message: 'Connected to web viewer',
        timestamp: Date.now(),
      }),
    );

    // Send current state snapshot so the client doesn't see all zeroes
    if (getStateSnapshot) {
      getStateSnapshot().then((state) => {
        if (state.orchestrator) {
          ws.send(JSON.stringify({ type: 'state_update', orchestrator: state.orchestrator }));
        }
        if (state.session) {
          ws.send(JSON.stringify({ type: 'state_update', session: state.session }));
        }
        if (state.plan) {
          ws.send(JSON.stringify({ type: 'state_update', plan: state.plan }));
        }
        if (state.plans && Object.keys(state.plans as object).length > 0) {
          ws.send(JSON.stringify({ type: 'state_update', plans: state.plans }));
        }
        if (state.pipelines && Object.keys(state.pipelines as object).length > 0) {
          ws.send(JSON.stringify({ type: 'state_update', pipelines: state.pipelines }));
        }
      }).catch((err: Error) => {
        console.error('Failed to send initial state to client:', err);
      });
    }

    ws.on('message', (data: Buffer) => {
      try {
        const message = JSON.parse(data.toString());
        console.log('Received message from client:', message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    });

    ws.on('close', () => {
      console.log('WebSocket client disconnected');
    });

    ws.on('error', (error) => {
      console.error('WebSocket error:', error);
    });
  });

  wss.on('error', (error) => {
    console.error('WebSocket server error:', error);
  });

  console.log(`WebSocket server ready at ws://localhost:${path}`);

  return wss;
}

export function broadcast(wss: WebSocketServer, message: object): void {
  const data = JSON.stringify(message);

  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(data);
    }
  });
}
