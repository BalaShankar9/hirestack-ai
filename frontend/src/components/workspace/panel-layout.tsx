"use client";

import { memo, type ReactNode } from "react";

interface PanelLayoutProps {
  mainPanel: ReactNode;
  contextPanel: ReactNode;
  bottomPanel?: ReactNode;
}

export const PanelLayout = memo(function PanelLayout({
  mainPanel,
  contextPanel,
  bottomPanel,
}: PanelLayoutProps) {
  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <div className={`flex flex-1 min-h-0 ${bottomPanel ? "" : "h-full"}`}>
        <div className="flex-[65] min-w-0 overflow-y-auto p-4">
          {mainPanel}
        </div>
        <div className="w-px bg-border/50" />
        <div className="flex-[35] min-w-0 overflow-y-auto p-4 border-l border-border/50">
          {contextPanel}
        </div>
      </div>
      {bottomPanel && (
        <>
          <div className="h-px bg-border/50" />
          <div className="h-[25%] min-h-[40px] overflow-y-auto p-3 border-t border-border/50 bg-surface">
            {bottomPanel}
          </div>
        </>
      )}
    </div>
  );
});
