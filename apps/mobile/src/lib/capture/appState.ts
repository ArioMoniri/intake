/**
 * The app's foreground state as a zeroing trigger (INT-559, invariant 3).
 *
 * The dialogue and the voice-note pill both close whatever microphone is
 * open and zero its buffer the moment the app leaves the foreground; this is
 * the one subscription they share. The listener is read through a ref so the
 * subscription is made once and always sees the current closure.
 */
import { useEffect, useRef } from "react";
import { AppState, type AppStateStatus } from "react-native";

export function useAppStateChange(listener: (status: AppStateStatus) => void): void {
  const listenerRef = useRef(listener);
  listenerRef.current = listener;
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (status) => {
      listenerRef.current(status);
    });
    return () => subscription.remove();
  }, []);
}
