/**
 * INT-246 — the `__DEV__` fallback banner.
 *
 * The incident: a port forward to the speech box died, `reachableAsrBaseUrl()`
 * returned null, the typed steps took over silently BY DESIGN, and the
 * absence of any signal read as "the voice UI was never built". Hours went
 * into a feature that was merged and running.
 *
 * This is the smallest thing that makes that impossible twice: when the probe
 * finds no lane, the typed flow still runs untouched, and in dev a compact
 * strip says which bases were tried and how each one failed. It is not a
 * retry, not a control and not a state — it renders a report someone else
 * already took, and it points at `make voice-doctor` for the host-side answer.
 *
 * Every decision it makes is in lib/dev/voiceDiagnostic, which returns null
 * unless `__DEV__`. In production this component renders nothing, so the
 * patient-facing behaviour DialogueGate's docstring argues for — the quiet
 * fallback, no failure notice for a voice run that never started — is
 * untouched.
 */
import { StyleSheet, View } from "react-native";

import { AppText, useTheme } from "@/components/Themed";
import type { ReachabilityReport } from "@/lib/dev/hosts";
import { ttsLaneDiagnostic, voiceDiagnostic, type VoiceTiming } from "@/lib/dev/voiceDiagnostic";
import type { ClipLaneRecord } from "@/lib/dialogue/georgeClip";
import { radius, spacing } from "@/lib/theme";

interface DevVoiceBannerProps {
  /** The finished ASR probe, or null while the gate is still probing. */
  report: ReachabilityReport | null;
}

export function DevVoiceBanner({ report }: DevVoiceBannerProps) {
  const theme = useTheme();
  const diagnostic = voiceDiagnostic(report, __DEV__);
  if (diagnostic === null) {
    return null;
  }
  return (
    <View
      accessible
      style={[styles.banner, { backgroundColor: theme.surfaceRaised, borderColor: theme.border }]}
    >
      <AppText role="label">{diagnostic.title}</AppText>
      <AppText role="caption" color="inkSoft">
        {diagnostic.body}
      </AppText>
      {diagnostic.lines.map((line) => (
        <AppText key={line} role="caption" color="inkFaint">
          {line}
        </AppText>
      ))}
      <AppText role="caption" color="inkFaint">
        {diagnostic.hint}
      </AppText>
    </View>
  );
}

/**
 * INT-440 — the `__DEV__` strip for the agent's VOICE: names the lane that
 * spoke the current clip (`elevenlabs-bundled`, `elevenlabs-live`, or the
 * self-hosted tier with the closed-set reason George did not), plus the turn's
 * measured audio start and microphone peak. The decision is
 * lib/dev/voiceDiagnostic's `ttsLaneDiagnostic`; in production nothing renders.
 */
export function DevTtsLaneBanner({
  record,
  timing,
}: {
  record: ClipLaneRecord | null;
  timing?: VoiceTiming;
}) {
  const theme = useTheme();
  const diagnostic = ttsLaneDiagnostic(record, __DEV__, timing);
  if (diagnostic === null) {
    return null;
  }
  return (
    <View
      accessible
      style={[styles.inline, { backgroundColor: theme.surfaceRaised, borderColor: theme.border }]}
    >
      <AppText role="label">{diagnostic.title}</AppText>
      {diagnostic.lines.map((line) => (
        <AppText key={line} role="caption" color="inkFaint">
          {line}
        </AppText>
      ))}
      {diagnostic.hint === null ? null : (
        <AppText role="caption" color="inkFaint">
          {diagnostic.hint}
        </AppText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    borderRadius: radius.control,
    borderWidth: 1,
    gap: 2,
    marginHorizontal: spacing.screen,
    marginTop: spacing.sm,
    padding: spacing.sm,
  },
  // inside the transcript's padded scroller, so no horizontal margin of its own
  inline: {
    borderRadius: radius.control,
    borderWidth: 1,
    gap: 2,
    padding: spacing.sm,
  },
});
