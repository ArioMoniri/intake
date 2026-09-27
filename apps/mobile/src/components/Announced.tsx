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
 * - `warning` is assertive and is spoken as shown: something happens soon
 *   unless the patient acts, and nothing went wrong (INT-363, the kiosk idle
 *   warning);
 * - `status` is polite and is spoken as shown.
 *
 * e2e/a11y.spec.ts finds every error and status line in the source tree and
 * fails on one that is not inside one of these two, and on any live region
 * declared anywhere else.
 *
 * INT-397 adds lines that state an OUTCOME, which stay on screen for as long
 * as it is so: the note was sent, a consent change waits, a setting did not
 * save. Such a line is announced when the outcome happens in front of the
 * patient and is shown without a word on every later visit. Its screen passes
 * `news={useNews(…)}`; every other line leaves `news` out and is announced
 * whenever it appears, exactly as before.
 *
 * PHI posture: the message is the line the screen already shows. Nothing here
 * composes a new statement (PolicyGuard, invariant 2), and what is spoken goes
 * to the OS screen reader only — never to a log (invariant 6).
 */
import { useIsFocused } from "expo-router";
import { useState, type ReactNode } from "react";
import { View, type StyleProp, type TextStyle, type ViewStyle } from "react-native";

import { AppText } from "@/components/Themed";
import { arrivedAt, newsStep, politenessOf, spokenLine, type LineTone } from "@/lib/a11y/announce";
import { useLineAnnouncement } from "@/lib/a11y/prefs";
import { t } from "@/lib/i18n";
import type { ThemeColors, TypeRole } from "@/lib/theme";

/**
 * Whether an outcome line is news on this render (INT-397; the rule is
 * `newsStep` in lib/a11y/announce, tested there).
 *
 * `standing` is the store's own state: the note's status is sent, the consent
 * outbox is held, the notification save failed. The outcome is news when that
 * state arrives while this screen is in front, and only then; whatever stands
 * when the screen is first rendered is old news. "In front" is the
 * navigator's focus, so the visit detail under the review screen stays quiet
 * when the note is sent from the review screen.
 *
 * The step is stored during render, React's pattern for information from
 * earlier renders, so the line is news in the very render it appears in.
 */
export function useNews(standing: boolean): boolean {
  const inFront = useIsFocused();
  const [memory, setMemory] = useState(() => arrivedAt(standing));
  const next = newsStep(memory, standing, inFront);
  if (next !== memory) {
    setMemory(next);
  }
  return next.news;
}

interface AnnouncedTextProps {
  /** `error` interrupts and is heard as an error; `warning` interrupts; `status` waits its turn. */
  tone: LineTone;
  /** The line's visible words — exactly what is rendered. */
  message: string;
  /**
   * Whether the line is news (INT-397). Left out, it is news whenever it is
   * shown, which is right for a line that appears only when something
   * happens. A line that states an outcome passes `useNews(…)`: while it is
   * not news it is shown with neither half, so a revisit is silent.
   */
  news?: boolean;
  role?: TypeRole;
  color?: keyof ThemeColors;
  heading?: boolean;
  style?: StyleProp<TextStyle>;
}

/** One error or status line: Android's live region and iOS's announcement. */
export function AnnouncedText({
  tone,
  message,
  news = true,
  role,
  color,
  heading,
  style,
}: AnnouncedTextProps) {
  const politeness = politenessOf(tone);
  const spoken = spokenLine(tone, message, t("a11y.error"));
  useLineAnnouncement(news ? spoken : null, politeness);
  return (
    <AppText
      // TalkBack speaks a live region when it appears or its words change. A
      // line whose words stay put while it turns into news (a save that was
      // in flight and then failed) is made again, and appears with its region.
      key={news ? "news" : "shown"}
      role={role}
      color={color}
      heading={heading}
      style={style}
      live={news ? politeness : undefined}
      // The live region reads the element's name, so TalkBack hears the same
      // words VoiceOver is sent. Unset when they equal the visible copy. Kept
      // when the line is not news: an error found on arrival is still named
      // as one when the reader reaches it (SC 3.3.1).
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
