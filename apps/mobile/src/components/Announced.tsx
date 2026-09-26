/**
 * Error and status lines that announce themselves on BOTH platforms (INT-362;
 * WCAG 2.2 SC 3.3.1 Error Identification, SC 4.1.3 Status Messages).
 *
 * React Native gives the two screen readers different channels. TalkBack
 * hears a line through its `accessibilityLiveRegion`, which RN declares
 * `@platform android`. VoiceOver has no live regions and no alert trait: it
 * hears a line only when the app posts it with `announceForAccessibility`.
 * A line that sets one half is silent on the other phone — the INT-226 report
 * found three (the Doctor Link error, the record card's not-saved notice and
 * the record-reading line) that had only the Android half.
 *
 * So the two halves are put together here and nowhere else. `AnnouncedText`
 * is one line; `AnnouncedRegion` is a group of lines announced as one (a
 * spinner row, a title with its body). Both take a `tone` and derive the rest:
 *
 * - `error` is assertive and is spoken with the catalogue's error word first
 *   ("Hata: …"), so a screen-reader user can tell it from a hint;
 * - `status` is polite and is spoken as shown.
 *
 * e2e/a11y.spec.ts finds every error and status line in the source tree and
 * fails on one that is not inside one of these two, and on any live region
 * declared anywhere else.
 *
 * PHI posture: the message is the line the screen already shows. Nothing here
 * composes a new statement (PolicyGuard, invariant 2), and what is spoken goes
 * to the OS screen reader only — never to a log (invariant 6).
 */
import { type ReactNode } from "react";
import { View, type StyleProp, type TextStyle, type ViewStyle } from "react-native";

import { AppText } from "@/components/Themed";
import { politenessOf, spokenLine, type LineTone } from "@/lib/a11y/announce";
import { useLineAnnouncement } from "@/lib/a11y/prefs";
import { t } from "@/lib/i18n";
import type { ThemeColors, TypeRole } from "@/lib/theme";

interface AnnouncedTextProps {
  /** `error` interrupts and is heard as an error; `status` waits its turn. */
  tone: LineTone;
  /** The line's visible words — exactly what is rendered. */
  message: string;
  role?: TypeRole;
  color?: keyof ThemeColors;
  heading?: boolean;
  style?: StyleProp<TextStyle>;
}

/** One error or status line: Android's live region and iOS's announcement. */
export function AnnouncedText({ tone, message, role, color, heading, style }: AnnouncedTextProps) {
  const politeness = politenessOf(tone);
  const spoken = spokenLine(tone, message, t("a11y.error"));
  useLineAnnouncement(spoken, politeness);
  return (
    <AppText
      role={role}
      color={color}
      heading={heading}
      style={style}
      live={politeness}
      // The live region reads the element's name, so TalkBack hears the same
      // words VoiceOver is sent. Unset when they equal the visible copy.
      spokenAs={spoken === message ? undefined : spoken}
    >
      {message}
    </AppText>
  );
}

interface AnnouncedRegionProps {
  tone: LineTone;
  /**
   * The words the region's children show, joined (lib/a11y/labels) — what
   * VoiceOver is sent. Never more than the region displays.
   */
  message: string;
  /**
   * Present the region as ONE element named `message` (a spinner beside its
   * caption). Leave it false where a child must stay reachable on its own,
   * such as a heading.
   */
  merged?: boolean;
  style?: StyleProp<ViewStyle>;
  children: ReactNode;
}

/** A group of lines announced as one: Android's live region and iOS's announcement. */
export function AnnouncedRegion({
  tone,
  message,
  merged = false,
  style,
  children,
}: AnnouncedRegionProps) {
  const politeness = politenessOf(tone);
  const spoken = spokenLine(tone, message, t("a11y.error"));
  useLineAnnouncement(spoken, politeness);
  return (
    <View
      style={style}
      accessible={merged}
      accessibilityLabel={merged ? spoken : undefined}
      accessibilityLiveRegion={politeness}
    >
      {children}
    </View>
  );
}
