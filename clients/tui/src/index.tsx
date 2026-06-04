// Side-effect import: populate process.env from `.env` before any module
// that reads it is evaluated. Must be the very first import.
import './config/env-bootstrap';

import {render} from 'ink';

import {App} from './app';

/**
 * lhx-rag entrypoint. Renders the Ink tree and exits cleanly on Ctrl+C and
 * other process signals. Top-level await keeps the process alive until Ink
 * tears the screen back down.
 */
const instance = render(<App />, {
  exitOnCtrlC: false,
  patchConsole: true
});

const cleanup = (): void => {
  instance.unmount();
};

process.once('SIGINT', cleanup);
process.once('SIGTERM', cleanup);

await instance.waitUntilExit();
process.exit(0);
