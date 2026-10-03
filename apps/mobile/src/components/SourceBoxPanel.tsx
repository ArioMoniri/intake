/**
 * The provenance locator (INT-138): where on which page this line came from.
 *
 * INT-121 gives every extracted value a `SourceBox` — a page number and a
 * rectangle normalised to the page — and makes it a defaultless field, so a
 * value with no box is not a case to reject: it cannot be written down. This
 * panel is the patient-facing half of that guarantee.
 *
 * **It expresses provenance, never confidence.** No accuracy figure has been
 * measured for this pipeline and none may be invented (CLAUDE.md invariant 20,
 * HB-A13), so the honest answer to *"how do I know this is right?"* is not a
 * percentage. It is *here is where it came from* — a page-shaped frame with
 * the rectangle drawn on it, and the document itself one tap away.
 *
 * The frame carries no page IMAGE. Rendering a PDF page needs a renderer this
 * app does not ship, and a schematic that shows position honestly is better
 * than a thumbnail that shows content the patient can already open. The
 * full-fidelity provenance is the document, and `records.prov.open` is it.
 */
import { StyleSheet, View } from "react-native";

import { AppText, SecondaryButton, useTheme } from "@/components/Themed";
import { joinParts } from "@/lib/a11y/labels";
import { t } from "@/lib/i18n";
import { boxFrame, boxRegionKey, pageAtom, type SourceBox } from "@/lib/records/extraction";
import { radius, spacing } from "@/lib/theme";

/** ISO 216 portrait — the shape of nearly every Turkish lab report. */
const PAGE_ASPECT = 1 / Math.SQRT2;

interface SourceBoxPanelProps {
  box: SourceBox;
  /** The name the patient gave the file, where the device still knows it. */
  documentName: string | null;
  onOpen: () => void;
}

export function SourceBoxPanel({ box, documentName, onOpen }: SourceBoxPanelProps) {
  const theme = useTheme();
  const frame = boxFrame(box.bbox);
  const where = joinParts(pageAtom(box.page), t(boxRegionKey(box.bbox)));
  return (
    <View style={styles.panel}>
      <View style={styles.locator}>
        <View
          accessibilityRole="image"
          accessibilityLabel={joinParts(t("records.prov.figure"), where)}
          style={[styles.page, { backgroundColor: theme.surface, borderColor: theme.border }]}
        >
          <View
            // Decoration inside a named figure: the label already says where
            // the rectangle sits, and a second element would announce the same
            // fact twice with no words of its own.
            accessibilityElementsHidden
            importantForAccessibility="no"
            style={[
              styles.highlight,
              frame as object,
              { backgroundColor: theme.primarySoft, borderColor: theme.primary },
            ]}
          />
        </View>
        <View style={styles.caption}>
          <AppText role="label" color="ink">
            {where}
          </AppText>
          {documentName === null ? null : (
            <AppText role="caption" color="inkFaint">
              {documentName}
            </AppText>
          )}
        </View>
      </View>
      <SecondaryButton label={t("records.prov.open")} onPress={onOpen} />
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { gap: spacing.md },
  locator: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  page: {
    width: 72,
    aspectRatio: PAGE_ASPECT,
    borderRadius: radius.group / 2,
    borderCurve: "continuous",
    borderWidth: 1,
    overflow: "hidden",
  },
  // Positioned from the normalised rectangle: percentage offsets mean the
  // frame can be any size and the box still lands where the document put it.
  highlight: { position: "absolute", borderWidth: 1, borderRadius: 2 },
  caption: { flex: 1, gap: spacing.xs },
});
