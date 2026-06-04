// Side-effect import: populate process.env from `.env` before any module
// that reads it is evaluated. Must be the very first import.
import './config/env-bootstrap';

import {render} from 'ink';

import {App} from './app';

/**
 * lhx-rag entrypoint. Renders the Ink tree and exits cleanly on Ctrl+C and
 * other process signals.
 *
 * Fullscreen behaviour
 * --------------------
 * We switch the terminal into the "alternate screen buffer" (the same trick
 * vim / less / htop use) so the TUI owns the whole viewport while running and
 * the user's previous shell scrollback is restored verbatim on exit.
 *
 *   ESC[?1049h  enter alt screen + save cursor
 *   ESC[?1049l  leave alt screen + restore cursor
 *
 * Ink's own ``render`` writes line-by-line into whatever buffer is current,
 * so we just toggle the buffer around it. Disable when the stream isn't a
 * TTY (e.g. piped output, CI logs) — alt-screen sequences in a logfile would
 * just look like noise.
 */
const FULLSCREEN_ENABLED =
  process.stdout.isTTY && process.env['LHX_RAG_NO_FULLSCREEN'] !== '1';

if (FULLSCREEN_ENABLED) {
  process.stdout.write('\x1b[?1049h\x1b[H');
}

const instance = render(<App />, {
  exitOnCtrlC: false,
  patchConsole: true
});

let teardown = false;
const cleanup = (): void => {
  if (teardown) return;
  teardown = true;
  try {
    instance.unmount();
  } catch {
    // ignore — already unmounted
  }
  if (FULLSCREEN_ENABLED) {
    // Leave the alt screen *after* Ink has stopped writing so the final
    // frame doesn't bleed back into the user's scrollback.
    process.stdout.write('\x1b[?1049l');
  }
};

process.once('SIGINT', cleanup);
process.once('SIGTERM', cleanup);
process.once('exit', cleanup);

await instance.waitUntilExit();
cleanup();
process.exit(0);
