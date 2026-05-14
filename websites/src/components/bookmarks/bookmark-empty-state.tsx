/** Shown on the bookmarks page when the user has saved nothing yet. */
export function BookmarkEmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center">
      <p className="text-sm font-medium">No bookmarks yet</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Open any answer in chat and click the bookmark icon to save it here.
      </p>
    </div>
  );
}
