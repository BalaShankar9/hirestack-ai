"use client";

import { memo, type ReactNode } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

interface PanelLayoutProps {
  mainPanel: ReactNode;
  contextPanel: ReactNode;
  bottomPanel?: ReactNode;
}

function ResizeHandle({ direction = "horizontal" }: { direction?: "horizontal" | "vertical" }) {
  return (
    <PanelResizeHandle
      className={
        direction === "horizontal"
          ? "w-1 hover:w-1.5 bg-border/50 hover:bg-primary/30 transition-all duration-150 cursor-col-resize"
          : "h-1 hover:h-1.5 bg-border/50 hover:bg-primary/30 transition-all duration-150 cursor-row-resize"
      }
    />
  );
}

export const PanelLayout = memo(function PanelLayout({
  mainPanel,
  contextPanel,
  bottomPanel,
}: PanelLayoutProps) {
  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <PanelGroup direction="vertical">
        <Panel defaultSize={bottomPanel ? 75 : 100} minSize={40}>
          <PanelGroup direction="horizontal">
            <Panel defaultSize={65} minSize={30}>
              <div className="h-full overflow-y-auto p-4">{mainPanel}</div>
            </Panel>
            <ResizeHandle direction="horizontal" />
            <Panel defaultSize={35} minSize={20}>
              <div className="h-full overflow-y-auto p-4 border-l border-border/50">
                {contextPanel}
              </div>
            </Panel>
          </PanelGroup>
        </Panel>
        {bottomPanel && (
          <>
            <ResizeHandle direction="vertical" />
            <Panel defaultSize={25} minSize={5} collapsible collapsedSize={3}>
              <div className="h-full overflow-y-auto p-3 border-t border-border/50 bg-surface">
                {bottomPanel}
              </div>
            </Panel>
          </>
        )}
      </PanelGroup>
    </div>
  );
});
