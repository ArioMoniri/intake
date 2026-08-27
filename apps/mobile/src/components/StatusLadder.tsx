/**
 * The 02 §5.1 status ladder as a vertical timeline: Taslak → Gönderildi →
 * Hekim görüntüledi → Dosyaya eklendi. Reached steps carry the accent; the
 * label always carries the meaning (colour never alone — 02 §8.2).
 */
import { StyleSheet, View } from "react-native";

import { AppText, useTheme } from "@/components/Themed";
import type { NoteStatus } from "@/lib/dev/accounts";
import { t } from "@/lib/i18n";
import { radius, spacing } from "@/lib/theme";

const LADDER: {
  status: NoteStatus;
  key: "status.draft" | "status.sent" | "status.viewed" | "status.filed";
}[] = [
  { status: "draft", key: "status.draft" },
  { status: "sent", key: "status.sent" },
  { status: "viewed", key: "status.viewed" },
  { status: "filed", key: "status.filed" },
];

export function StatusLadder({ current }: { current: NoteStatus }) {
  const theme = useTheme();
  const reachedIndex = LADDER.findIndex((s) => s.status === current);
  return (
    <View style={styles.column}>
      {LADDER.map((step, i) => {
        const reached = i <= reachedIndex;
        const nextReached = i + 1 <= reachedIndex;
        return (
          <View key={step.status} style={styles.row}>
            <View style={styles.rail}>
              <View
                style={[
                  styles.dot,
                  {
                    backgroundColor: reached ? theme.primary : theme.background,
                    borderColor: reached ? theme.primary : theme.border,
                  },
                ]}
              />
              {i < LADDER.length - 1 ? (
                <View
                  style={[
                    styles.connector,
                    { backgroundColor: nextReached ? theme.primary : theme.border },
                  ]}
                />
              ) : null}
            </View>
            <AppText
              role="body"
              color={reached ? "ink" : "inkFaint"}
              style={reached && i === reachedIndex ? styles.current : undefined}
            >
              {t(step.key)}
            </AppText>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  column: {},
  row: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  rail: { alignItems: "center", width: 14 },
  dot: { width: 14, height: 14, borderRadius: radius.chip, borderWidth: 2, marginTop: 4 },
  connector: { width: 2, height: 22, marginVertical: 2, borderRadius: 1 },
  current: { fontWeight: "600" },
});
