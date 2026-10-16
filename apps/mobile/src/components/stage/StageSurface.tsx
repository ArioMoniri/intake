/**
 * The stage surface for a screen's content (ADR-039 amendment, INT-499).
 *
 * On the visits list, documents, the share centre and settings the content
 * keeps its shared components (grouped lists, cards, segments, secondary
 * buttons) and takes the stage's solid card at the stage corner from here,
 * so a screen sets its surface once rather than threading it through every
 * row. Outside a provider nothing changes: `useStageSurface()` is null and
 * the components draw the system grounds as before.
 *
 * Content only: the surface is a solid fill, never a material, and the
 * provider draws nothing itself. Glass stays on the page actions
 * (`StageButton`), as Apple's guidance keeps it on the control layer.
 */
import { createContext, useContext, type ReactNode } from "react";

import type { StagePalette } from "@/lib/stage/palette";
import { stageSurface, type StageSurface } from "@/lib/stage/screens";

const SurfaceContext = createContext<StageSurface | null>(null);

export function StageSurfaceProvider({
  palette,
  children,
}: {
  palette: StagePalette;
  children: ReactNode;
}) {
  return (
    <SurfaceContext.Provider value={stageSurface(palette)}>{children}</SurfaceContext.Provider>
  );
}

/** The stage surface the content sits on, or null off the stage. */
export function useStageSurface(): StageSurface | null {
  return useContext(SurfaceContext);
}
