import {useEffect, useState} from 'react';

/**
 * React hook around process.stdout {columns,rows}. Re-renders the consumer on
 * SIGWINCH so layouts can recompute breakpoints when the terminal is resized.
 */
export function useWindowSize(): {columns: number; rows: number} {
  const read = () => ({
    columns: process.stdout.columns ?? 80,
    rows: process.stdout.rows ?? 24
  });
  const [size, setSize] = useState(read);

  useEffect(() => {
    const handler = () => setSize(read());
    process.stdout.on('resize', handler);
    return () => {
      process.stdout.off('resize', handler);
    };
  }, []);

  return size;
}
