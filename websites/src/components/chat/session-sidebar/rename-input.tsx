"use client";

import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";

/** Inline rename field for a session row — commits on Enter or blur. */
export function RenameInput({
  initial,
  onCommit,
  onCancel,
}: {
  initial: string;
  onCommit: (next: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const inputRef = useRef<HTMLInputElement>(null);
  // Guard against double-fire (Enter then blur).
  const committed = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const commit = () => {
    if (committed.current) return;
    committed.current = true;
    onCommit(value);
  };

  return (
    <div className="min-w-0 flex-1 px-2 py-1.5">
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            committed.current = true;
            onCancel();
          }
        }}
        onBlur={commit}
        maxLength={256}
        aria-label="Rename conversation"
        className="h-8 text-sm"
      />
    </div>
  );
}
