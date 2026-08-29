/**
 * Audio-only WebRTC config plugin (INT-103).
 *
 * `@livekit/react-native-expo-plugin` is registered alongside this one, but it
 * only writes meta-data (Android audio type, screen-share and multitasking
 * camera switches) — it declares NO permissions. LiveKit's own instructions
 * pair it with `@config-plugins/react-native-webrtc`, which we deliberately do
 * NOT use: that plugin declares the CAMERA permission and the camera usage
 * description, and this app has no video path at all. The SFU enables
 * `audio/opus` as its sole codec (infra/livekit/livekit-dev.yaml) and the room
 * token grants `canPublishSources: ["microphone"]` and nothing else
 * (INT-090), so a camera permission would be a store-review liability
 * requesting access to a sensor the product cannot use.
 *
 * So this plugin declares exactly the audio-only set, and actively REMOVES
 * camera permissions if any dependency's manifest merge introduces one.
 *
 * TWO THINGS IT DELIBERATELY DOES NOT DO:
 *
 * 1. It does not add the iOS `audio` UIBackgroundMode, and it strips one if
 *    present. The INT-103 acceptance is "background pauses safely": the
 *    session mutes the microphone at the source when the app leaves the
 *    foreground. Declaring background audio would let capture continue behind
 *    a backgrounded medical app — the opposite of the requirement, and an
 *    App Review question we would have no good answer to.
 *
 * 2. It does not write NSMicrophoneUsageDescription. That string is already
 *    localised through `expo.locales` (src/locales/app-tr.json and
 *    app-en.json), which is the right mechanism for a Turkish-first app:
 *    Apple shows the string in the user's own language, and tr stays the
 *    source of truth (invariant 5). A hardcoded English default here would
 *    quietly outrank the localised file on some builds.
 *
 * Expo Go never runs plugin output, so none of this applies there — which is
 * exactly why src/lib/livekit/capability.ts reports `needs_dev_build` instead
 * of pretending the transport exists.
 */
const { withAndroidManifest, withInfoPlist } = require("expo/config-plugins");

/**
 * The audio-only WebRTC permission set.
 * - RECORD_AUDIO          capture the microphone (the whole point).
 * - MODIFY_AUDIO_SETTINGS switch to the communication audio mode, route to
 *                         earpiece/speaker, and manage echo cancellation.
 * - ACCESS_NETWORK_STATE  detect network transitions so ICE can restart
 *                         promptly instead of waiting for a timeout.
 * - BLUETOOTH_CONNECT     route to a Bluetooth headset on Android 12+.
 *                         Without it a paired headset is silently skipped.
 */
const AUDIO_PERMISSIONS = [
  "android.permission.RECORD_AUDIO",
  "android.permission.MODIFY_AUDIO_SETTINGS",
  "android.permission.ACCESS_NETWORK_STATE",
  "android.permission.BLUETOOTH_CONNECT",
];

/** Never declared: this app has no video path. */
const FORBIDDEN_PERMISSIONS = ["android.permission.CAMERA"];

function withAudioOnlyPermissions(config) {
  return withAndroidManifest(config, (modConfig) => {
    const manifest = modConfig.modResults.manifest;
    const existing = manifest["uses-permission"] ?? [];
    const kept = existing.filter(
      (entry) => !FORBIDDEN_PERMISSIONS.includes(entry?.$?.["android:name"]),
    );
    const declared = new Set(kept.map((entry) => entry?.$?.["android:name"]));
    for (const name of AUDIO_PERMISSIONS) {
      if (!declared.has(name)) {
        kept.push({ $: { "android:name": name } });
      }
    }
    manifest["uses-permission"] = kept;
    return modConfig;
  });
}

function withoutBackgroundAudio(config) {
  return withInfoPlist(config, (modConfig) => {
    const modes = modConfig.modResults.UIBackgroundModes;
    if (!Array.isArray(modes)) {
      return modConfig;
    }
    const kept = modes.filter((mode) => mode !== "audio" && mode !== "voip");
    if (kept.length === 0) {
      delete modConfig.modResults.UIBackgroundModes;
    } else {
      modConfig.modResults.UIBackgroundModes = kept;
    }
    return modConfig;
  });
}

module.exports = function withVoiceAudio(config) {
  return withoutBackgroundAudio(withAudioOnlyPermissions(config));
};
