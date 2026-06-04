import {loadDotEnv} from './env';

// Side-effect entry: imported once from src/index.tsx so that running via
// `tsx` (no rslib bundle) still picks up `.env`. The bundled build is
// already self-contained — rslib substitutes process.env.* at compile time
// — but calling this is harmless there too.
loadDotEnv();
