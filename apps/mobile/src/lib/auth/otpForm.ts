/**
 * The SMS-code form's geometry and countdown line (INT-601, design audit A6).
 *
 * On main the six boxes were a fixed 48 pt each in a row that could not wrap:
 * in a 320 pt window (Android at the "Large" display size) the row ran from
 * x = -4 to 324, and at text step 2.0 the digit filled its box. Here the box
 * width comes from the room the card actually has, between a floor and a
 * ceiling that both grow with the text. Where six boxes of the floor width do
 * not fit, and at `LARGE_TEXT_SCALE`, the code is laid out as two rows of
 * three: a form change, as the rail and the segmented control make, never a
 * clamp on the digit.
 *
 * Pure: no react-native import, so it is unit-tested in node.
 */
import { NBSP } from "../health/format";
import { t, type Locale } from "../i18n";
import { isLargeText } from "../prefs/appearance";
import { scaledControl, scaledSize, spacing } from "../theme";
import { OTP_LENGTH } from "./phone";

/** Box bounds at fontScale 1.0, in pt. `height` is the base of the scaled height. */
export const OTP_BOX = { min: 40, max: 56, height: 56 } as const;

/**
 * The narrowest window the layout is held to: Android at the "Large" display
 * size (about 320 dp), and the stand-in width before the card is measured.
 */
export const OTP_NARROWEST_WINDOW = 320;

/** The card's hairline border, one point each side (Themed.tsx `card`). */
const CARD_BORDER = 1;

/**
 * The card's inner width in a window of `windowWidth`: the screen gutter, the
 * card's border and its padding off both sides. The padding is the tight one
 * at the large-text scale, as `Card` does (INT-260).
 */
export function otpAvailableWidth(windowWidth: number, fontScale: number): number {
  const padding = isLargeText(fontScale) ? spacing.md : spacing.lg;
  return windowWidth - 2 * spacing.screen - 2 * CARD_BORDER - 2 * padding;
}

export interface OtpLayout {
  /** Boxes per row: all six, or three in two rows. */
  readonly perRow: 6 | 3;
  readonly box: number;
  readonly height: number;
  readonly gap: number;
  readonly fontSize: number;
}

export function otpLayout(available: number, fontScale: number): OtpLayout {
  const gap = spacing.sm;
  const fontSize = scaledSize("title", fontScale);
  const minBox = Math.max(OTP_BOX.min, fontSize);
  const maxBox = scaledControl(OTP_BOX.max, fontScale);
  const sixFit = OTP_LENGTH * minBox + (OTP_LENGTH - 1) * gap <= available;
  const perRow: 6 | 3 = !isLargeText(fontScale) && sixFit ? 6 : 3;
  const box = Math.min(maxBox, Math.floor((available - (perRow - 1) * gap) / perRow));
  return {
    perRow,
    box,
    height: scaledControl(OTP_BOX.height, fontScale),
    gap,
    fontSize,
  };
}

/**
 * "Yeni kod isteyebilmek için kalan süre: 58 saniye". The number and its unit
 * are one non-breaking atom with no digit grouping, so the unit never wraps
 * away from the number it belongs to.
 */
export function resendWaitLine(seconds: number, locale?: Locale): string {
  const count = String(Math.max(0, Math.trunc(seconds)));
  return `${t("auth.otp.resendWait", locale)} ${count}${NBSP}${t("auth.otp.resendUnit", locale)}`;
}
