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
      <div className={`flex flex-col lg:flex-row flex-1 min-h-0 ${bottomPanel ? "" : "h-full"}`}>
        <div className="flex-1 lg:flex-[65] min-w-0 overflow-y-auto p-3 sm:p-4">
          {mainPanel}
        </div>
        <div className="hidden lg:block w-px bg-border/50" />
        <div className="h-px lg:hidden bg-border/50" />
        <div className="flex-none lg:flex-[35] min-w-0 overflow-y-auto p-3 sm:p-4 border-t lg:border-t-0 lg:border-l border-border/50 max-h-[40vh] lg:max-h-none">
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
