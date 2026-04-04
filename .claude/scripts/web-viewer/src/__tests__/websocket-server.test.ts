import { describe, it, expect, vi, afterEach } from 'vitest';
import { createServer } from 'http';
import WebSocket, { WebSocketServer } from 'ws';
import { createWebSocketServer, broadcast } from '../../src/websocket-server.js';

import type { Server } from 'http';

let httpServer: Server | undefined;
let wss: WebSocketServer | undefined;
let client: WebSocket | undefined;

afterEach(async () => {
  if (client && client.readyState !== WebSocket.CLOSED) {
    client.close();
    await new Promise<void>((resolve) => {
      client!.once('close', () => resolve());
      setTimeout(resolve, 500);
    });
  }
  client = undefined;

  if (wss) {
    wss.close();
    wss = undefined;
  }

  if (httpServer) {
    await new Promise<void>((resolve) => {
      httpServer!.close(() => resolve());
    });
    httpServer = undefined;
  }
});

/**
 * Collect the next N messages from a WebSocket client.
 * Sets up the listener immediately (before open), so no messages are lost.
 */
function collectMessages(
  ws: WebSocket,
  count: number,
  timeout = 5000,
): Promise<Record<string, unknown>[]> {
  return new Promise((resolve, reject) => {
    const messages: Record<string, unknown>[] = [];
    const timer = setTimeout(
      () => reject(new Error(`Timeout: received ${messages.length}/${count} messages after ${timeout}ms`)),
      timeout,
    );

    const onMessage = (data: Buffer) => {
      messages.push(JSON.parse(data.toString()));
      if (messages.length >= count) {
        clearTimeout(timer);
        ws.removeListener('message', onMessage);
        resolve(messages);
      }
    };

    ws.on('message', onMessage);
  });
}

async function setupServerAndConnect(): Promise<{ port: number }> {
  httpServer = createServer();
  wss = createWebSocketServer({ httpServer, path: '/ws' });

  await new Promise<void>((resolve) => {
    httpServer!.listen(0, () => resolve());
  });

  const port = (httpServer.address() as { port: number }).port;
  return { port };
}

describe('broadcast', () => {
  it('sends JSON to all connected clients with OPEN readyState', () => {
    const mockClient1 = { readyState: WebSocket.OPEN, send: vi.fn() };
    const mockClient2 = { readyState: WebSocket.OPEN, send: vi.fn() };
    const mockWss = { clients: new Set([mockClient1, mockClient2]) };

    broadcast(mockWss as unknown as WebSocketServer, { type: 'test', data: 'hello' });

    const expected = JSON.stringify({ type: 'test', data: 'hello' });
    expect(mockClient1.send).toHaveBeenCalledWith(expected);
    expect(mockClient2.send).toHaveBeenCalledWith(expected);
  });

  it('skips clients not in OPEN state', () => {
    const openClient = { readyState: WebSocket.OPEN, send: vi.fn() };
    const closingClient = { readyState: WebSocket.CLOSING, send: vi.fn() };
    const closedClient = { readyState: WebSocket.CLOSED, send: vi.fn() };
    const connectingClient = { readyState: WebSocket.CONNECTING, send: vi.fn() };

    const mockWss = {
      clients: new Set([openClient, closingClient, closedClient, connectingClient]),
    };

    broadcast(mockWss as unknown as WebSocketServer, { type: 'test' });

    expect(openClient.send).toHaveBeenCalledTimes(1);
    expect(closingClient.send).not.toHaveBeenCalled();
    expect(closedClient.send).not.toHaveBeenCalled();
    expect(connectingClient.send).not.toHaveBeenCalled();
  });

  it('handles empty clients set', () => {
    const mockWss = { clients: new Set() };

    expect(() => {
      broadcast(mockWss as unknown as WebSocketServer, { type: 'test' });
    }).not.toThrow();
  });

  it('serializes message to JSON string', () => {
    const mockClient = { readyState: WebSocket.OPEN, send: vi.fn() };
    const mockWss = { clients: new Set([mockClient]) };
    const message = { type: 'state_update', data: { count: 42 } };

    broadcast(mockWss as unknown as WebSocketServer, message);

    expect(mockClient.send).toHaveBeenCalledWith(JSON.stringify(message));
  });
});

describe('createWebSocketServer', () => {
  it('returns a WebSocketServer instance', () => {
    httpServer = createServer();
    wss = createWebSocketServer({ httpServer, path: '/ws' });
    expect(wss).toBeInstanceOf(WebSocketServer);
  });

  it('connected client receives connection confirmation message', async () => {
    const { port } = await setupServerAndConnect();

    client = new WebSocket(`ws://localhost:${port}/ws`);

    // Set up message collection BEFORE connection opens to avoid race
    const messagesPromise = collectMessages(client, 1);

    const [message] = await messagesPromise;
    expect(message.type).toBe('connection');
    expect(message.message).toBe('Connected to web viewer');
    expect(message.timestamp).toBeTypeOf('number');
  });

  it('sends initial state snapshot when getStateSnapshot is provided', async () => {
    httpServer = createServer();

    const mockState = {
      orchestrator: { version: '1.0', agents: { activeCount: 2 } },
      session: null,
      plan: null,
      plans: {},
    };

    wss = createWebSocketServer({
      httpServer,
      path: '/ws',
      getStateSnapshot: () => Promise.resolve(mockState),
    });

    await new Promise<void>((resolve) => {
      httpServer!.listen(0, () => resolve());
    });

    const port = (httpServer!.address() as { port: number }).port;
    client = new WebSocket(`ws://localhost:${port}/ws`);

    // Collect 2 messages: connection confirmation + orchestrator state
    const messages = await collectMessages(client, 2);

    expect(messages[0].type).toBe('connection');
    expect(messages[1].type).toBe('state_update');
    expect((messages[1] as Record<string, unknown>).orchestrator).toEqual(mockState.orchestrator);
  });
});
