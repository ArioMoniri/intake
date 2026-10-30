/**
 * The symbol registry (docs/design/apple-native/spec.md §1.2): every glyph
 * the app draws, as one row with an SF Symbol for iOS and a Material Symbol
 * for Android and web.
 *
 * Why a registry. expo-symbols treats a bare string `name` as an iOS-only SF
 * name and renders its `fallback` on every other platform. Before this file,
 * every call site passed a bare string and none passed a fallback, so on
 * Android the tab rail, every chevron and the send arrow drew nothing. SF
 * Symbols are also licensed only for UI on Apple platforms, so the Android
 * and web half has to be a different glyph set: Material Symbols (Apache-2.0),
 * which expo-symbols already bundles.
 *
 * The key is the SF name the call sites already used, so a call site still
 * reads as the glyph it draws. `selected` is the filled SF variant the tab
 * rail shows for the active section (HIG tab bars), where SF has one. It is
 * a shape cue beside the rail's ink and weight, so the state is never carried
 * by tint alone (BK8 / SC 1.4.1).
 *
 * Pure: only types come from expo-symbols, so symbols.test.ts can check every
 * row in node against the name sets the app ships. The one importer of the
 * native module is components/Icon.tsx.
 */
import type { AndroidSymbol, SFSymbol } from "expo-symbols";

export interface SymbolEntry {
  /** The SF Symbol drawn on iOS. */
  readonly ios: SFSymbol;
  /** The filled SF variant for a selected state, where SF has one. */
  readonly selected?: SFSymbol;
  /** The Material Symbol drawn on Android and web. */
  readonly android: AndroidSymbol;
}

export const SYMBOLS = {
  // The tab rail.
  "sun.max": { ios: "sun.max", selected: "sun.max.fill", android: "light_mode" },
  calendar: { ios: "calendar", android: "calendar_month" },
  folder: { ios: "folder", selected: "folder.fill", android: "folder" },
  heart: { ios: "heart", selected: "heart.fill", android: "favorite" },
  "person.crop.circle": {
    ios: "person.crop.circle",
    selected: "person.crop.circle.fill",
    android: "account_circle",
  },
  // Navigation and disclosure.
  "chevron.left": { ios: "chevron.left", android: "chevron_left" },
  "chevron.right": { ios: "chevron.right", android: "chevron_right" },
  "chevron.up": { ios: "chevron.up", android: "keyboard_arrow_up" },
  "arrow.up": { ios: "arrow.up", android: "arrow_upward" },
  checkmark: { ios: "checkmark", android: "check" },
  // Row and primer marks.
  "person.2": { ios: "person.2", android: "group" },
  paperplane: { ios: "paperplane", android: "send" },
  "doc.text": { ios: "doc.text", android: "description" },
  "doc.text.magnifyingglass": { ios: "doc.text.magnifyingglass", android: "find_in_page" },
  photo: { ios: "photo", android: "image" },
  "wifi.slash": { ios: "wifi.slash", android: "wifi_off" },
  "checkmark.shield": { ios: "checkmark.shield", android: "verified_user" },
  "lock.shield": { ios: "lock.shield", android: "shield_lock" },
  // INT-582: the patient passkey row
  key: { ios: "key", android: "key" },
  "tray.and.arrow.down": { ios: "tray.and.arrow.down", android: "download" },
  trash: { ios: "trash", android: "delete" },
  bell: { ios: "bell", android: "notifications" },
  "textformat.size": { ios: "textformat.size", android: "format_size" },
  eye: { ios: "eye", android: "visibility" },
} as const satisfies Record<string, SymbolEntry>;

export type SymbolKey = keyof typeof SYMBOLS;

/** The object form of expo-symbols' `name` prop: one name per platform. */
export interface PlatformSymbolName {
  readonly ios: SFSymbol;
  readonly android: AndroidSymbol;
  readonly web: AndroidSymbol;
}

/**
 * The name SymbolView needs for `key`. It is always the object form, because
 * a string is iOS-only. Web takes the Material twin, because SF glyphs are
 * for Apple platforms only.
 */
export function symbolName(key: SymbolKey, selected = false): PlatformSymbolName {
  const entry: SymbolEntry = SYMBOLS[key];
  const ios = selected && entry.selected !== undefined ? entry.selected : entry.ios;
  return { ios, android: entry.android, web: entry.android };
}
