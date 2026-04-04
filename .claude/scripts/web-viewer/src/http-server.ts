import * as http from 'node:http';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';

interface HttpServerOptions {
  port: number;
  publicDir: string;
}

const MIME_TYPES: Record<string, string> = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
};

export function createHttpServer(options: HttpServerOptions): http.Server {
  const { publicDir } = options;

  const server = http.createServer(async (req, res) => {
    try {
      // Default to index.html for root path
      let filePath = req.url === '/' ? '/index.html' : req.url || '/index.html';

      // Remove query strings
      const queryIndex = filePath.indexOf('?');
      if (queryIndex !== -1) {
        filePath = filePath.substring(0, queryIndex);
      }

      // Decode percent-encoding (e.g. %20). Reject invalid encodings.
      try {
        filePath = decodeURIComponent(filePath);
      } catch {
        res.writeHead(400, { 'Content-Type': 'text/plain' });
        res.end('Bad Request');
        return;
      }

      // Resolve to absolute path (force relative-to-publicDir even for leading "/")
      if (!filePath.startsWith('/')) filePath = `/${filePath}`;
      const resolvedPublicDir = path.resolve(publicDir);
      const absolutePath = path.resolve(resolvedPublicDir, `.${filePath}`);

      // Security: ensure resolved path is within publicDir (directory-boundary safe)
      const relativeToPublicDir = path.relative(resolvedPublicDir, absolutePath);
      const isWithinPublicDir =
        relativeToPublicDir === '' ||
        (!relativeToPublicDir.startsWith(`..${path.sep}`) &&
          relativeToPublicDir !== '..' &&
          !path.isAbsolute(relativeToPublicDir));

      if (!isWithinPublicDir) {
        res.writeHead(403, { 'Content-Type': 'text/plain' });
        res.end('Forbidden');
        return;
      }

      // Read file
      const content = await fs.readFile(absolutePath);

      // Determine content type
      const ext = path.extname(filePath);
      const contentType = MIME_TYPES[ext] || 'application/octet-stream';

      // Send response
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('Not Found');
      } else {
        console.error('Server error:', error);
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        res.end('Internal Server Error');
      }
    }
  });

  return server;
}

export function startHttpServer(options: HttpServerOptions): Promise<http.Server> {
  return new Promise((resolve, reject) => {
    const server = createHttpServer(options);

    server.listen(options.port, () => {
      console.log(`HTTP server listening on http://localhost:${options.port}`);
      resolve(server);
    });

    server.on('error', reject);
  });
}
