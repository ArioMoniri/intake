/**
 * Audio-only WebRTC config plugin (INT-103).
 *
 * `@livekit/react-native-expo-plugin` is registered alongside this one, but it
 * only writes meta-data (Android audio type, screen-share and multitasking
 * camera switches) — it declares NO permissions. LiveKit's own instructions
 * pair it with `@config-plugins/react-native-webrtc`, which we deliberately do
 * NOT use: that plugin declares the CAMERA permission and the camera usage
 * description for a VIDEO path this product does not have. The SFU enables
 * `audio/opus` as its sole codec (infra/livekit/livekit-dev.yaml) and the room
 * token grants `canPublishSources: ["microphone"]` and nothing else (INT-090).
 *
 * So this plugin declares exactly the audio-only set, and blocks the
 * permissions no part of this product may ask for.
 *
 * CHANGED AT INT-138, and the change is worth stating plainly. This list held
 * `android.permission.CAMERA` and the reasoning was *"this app has no video
 * path at all"*, which was true until the records screen gained a camera
 * capture of the patient's own report. Two things follow, and they point the
 * same way:
 *
 * 1. The premise is gone — the product now uses the camera, for one still
 *    capture on one screen — so keeping the entry would deny a permission the
 *    product needs.
 * 2. The entry could not have delivered what it claimed anyway. `withAndroid
 *    Manifest` edits the APP manifest; `expo-image-picker`'s own library
 *    manifest declares CAMERA and merges it in at Gradle time regardless. A
 *    control that claims something it does not do is worse than none.
 *
 * The guarantee that entry stood for never lived here and is untouched: the
 * voice session cannot publish video because the ROOM TOKEN grants microphone
 * alone, the SFU carries one audio codec, and `enableMultitaskingCameraAccess`
 * is false. Those are server-side and transport-side controls, and a manifest
 * line was never one of them.
 *
 * What the list holds now is the other half of adding an image picker: its
 * library manifest also declares READ_/WRITE_EXTERNAL_STORAGE (maxSdkVersion
 * 32) for the camera-roll path this app never invokes — `launchCameraAsync`
 * and the document picker's SAF flow need neither. Broad storage access on
 * Android 12 and below, declared for a feature we do not use, is exactly the
 * over-declaration the original entry existed to prevent.
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
 *    quietly outrank the localised file on some builds. INT-138's
 *    NSCameraUsageDescription is declared the same way and for the same
 *    reason, which is also why `expo-image-picker`'s config plugin is NOT
 *    registered: passing it `microphonePermission: false` would block
 *    RECORD_AUDIO app-wide and silence the voice path, and omitting the field
 *    would write Apple's English default over the localised microphone string.
 *
 * Expo Go never runs plugin output, so none of this applies there — which is
 * exactly why src/lib/livekit/capability.ts reports `needs_dev_build` instead
 * of pretending the transport exists.
 */
const { AndroidConfig, withAndroidManifest, withInfoPlist } = require("expo/config-plugins");

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

/**
 * Never declared, by anything, including a merged library manifest. These are
 * removed with `tools:node="remove"` rather than filtered out of the app
 * manifest, because filtering reaches only what this file writes.
 */
const FORBIDDEN_PERMISSIONS = [
  "android.permission.READ_EXTERNAL_STORAGE",
  "android.permission.WRITE_EXTERNAL_STORAGE",
  // The location family is blocked rather than merely undeclared, and the
  // difference is the whole point of the mechanism: a permission this app never
  // writes can still arrive from a dependency's AAR at Gradle merge time, and
  // `expo.android.permissions` — the only thing a checklist can read before a
  // prebuild — would not show it. There is no code path in this product that
  // reads a position, and `records/store/checklist.py` requires every sensor
  // family to be either declared-with-a-path or blocked here.
  "android.permission.ACCESS_FINE_LOCATION",
  "android.permission.ACCESS_COARSE_LOCATION",
  "android.permission.ACCESS_BACKGROUND_LOCATION",
];

function withAudioOnlyPermissions(config) {
  const blocked = AndroidConfig.Permissions.withBlockedPermissions(config, FORBIDDEN_PERMISSIONS);
  return withAndroidManifest(blocked, (modConfig) => {
    const manifest = modConfig.modResults.manifest;
    const kept = manifest["uses-permission"] ?? [];
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
