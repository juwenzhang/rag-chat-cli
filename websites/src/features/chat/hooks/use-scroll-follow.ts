"use client";

import { useCallback, useEffect, type RefObject } from "react";

interface Params {
  scrollRef: RefObject<HTMLDivElement | null>;
  /** Mutable boolean ref — flipped by the scroll listener and read by the auto-scroll effect. */
  stickToBottomRef: RefObject<boolean>;
  /** Any value that triggers re-scroll-to-bottom when it changes (typically the message list). */
  messages: unknown[];
  /** Called when the user's scroll position crosses the "near bottom" threshold. */
  setAtBottom: (next: boolean) => void;
}

/**
 * Auto-scroll-to-bottom behavior with stickiness — typical chat UX.
 *
 * Two effects:
 *  1. Track scroll position; flip ``stickToBottomRef`` when the user
 *     is within ~80 px of the bottom.
 *  2. When ``messages`` changes and we're sticky, jump to the bottom.
 *
 * Threshold (80 px) is a small slack so a one-line autocomplete in the
 * composer doesn't unstick the view.
 */
export function useScrollFollow({
  scrollRef,
  stickToBottomRef,
  messages,
  setAtBottom,
}: Params): void {
  const isNearBottom = useCallback((el: HTMLElement) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const near = isNearBottom(el);
      stickToBottomRef.current = near;
      setAtBottom(near);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isNearBottom, scrollRef, setAtBottom, stickToBottomRef]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (!stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, scrollRef, stickToBottomRef]);
}
