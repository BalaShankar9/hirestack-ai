"use client";

import { useEffect, useState } from "react";
import { Command as Cmdk } from "cmdk";
import { useCommands } from "./use-commands";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const commands = useCommands();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  if (!open) return null;

  const categories = ["recent", "actions", "navigate"] as const;

  return (
    <div className="fixed inset-0 z-50" onClick={() => setOpen(false)}>
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" />
      <div className="fixed top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <Cmdk
          className="glass-panel rounded-xl border border-white/20 shadow-2xl overflow-hidden"
          label="Command palette"
        >
          <Cmdk.Input
            placeholder="Type a command or search..."
            className="w-full px-4 py-3 text-sm bg-transparent border-b border-white/10 outline-none placeholder:text-muted-foreground"
            autoFocus
          />
          <Cmdk.List className="max-h-72 overflow-y-auto p-2">
            <Cmdk.Empty className="px-4 py-6 text-sm text-muted-foreground text-center">
              No results found.
            </Cmdk.Empty>
            {categories.map((cat) => {
              const items = commands.filter((c) => c.category === cat);
              if (items.length === 0) return null;
              return (
                <Cmdk.Group
                  key={cat}
                  heading={cat.charAt(0).toUpperCase() + cat.slice(1)}
                  className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground"
                >
                  {items.map((cmd) => (
                    <Cmdk.Item
                      key={cmd.id}
                      value={cmd.label}
                      onSelect={() => {
                        cmd.onSelect();
                        setOpen(false);
                      }}
                      className="flex items-center justify-between px-3 py-2 text-sm rounded-lg cursor-pointer aria-selected:bg-primary/10 aria-selected:text-primary"
                    >
                      <span>{cmd.label}</span>
                      {cmd.shortcut && (
                        <kbd className="font-mono text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </Cmdk.Item>
                  ))}
                </Cmdk.Group>
              );
            })}
          </Cmdk.List>
        </Cmdk>
      </div>
    </div>
  );
}
