/**
 * Kiosk gate (INT-143, files/10 §4 / §9 "Check-in / kiosk").
 *
 * Wraps the whole app. On a normal phone it is a pass-through — the MDM
 * managed-config read returns null, so `isKioskProvisioned` is false and
 * children render untouched. On a device a clinic has provisioned as a kiosk it
 * takes over: entering and leaving are gated by the staff-held clinic PIN, the
 * resting screen is a large-type privacy layout that reveals nothing about the
 * last patient, a lockdown that breaks raises a tamper alert rather than
 * degrading silently, and while a patient session is armed the session is
 * wiped after 60 s idle or on backgrounding (the timer and AppState listener
 * live in lib/kiosk/nativeKiosk.ts, reached lazily so this file stays off the
 * native path and off the a11y timer surface).
 *
 * The clinic PIN is verified against the MDM-provisioned salted hash and never
 * stored here (HUMAN_BLOCKERS.md Rule 1). No dev-only bypass exists: with no
 * provisioning the gate is simply a normal phone, and with no confirmed
 * lockdown a provisioned kiosk is tampered — both fail closed.
 */
import { useCallback, useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { ScrollView, StyleSheet, TextInput, View } from "react-native";

import {
  AppText,
  PrimaryButton,
  Screen,
  SecondaryButton,
  useFontScale,
  useTheme,
} from "@/components/Themed";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t } from "@/lib/i18n";
import {
  initialKioskMode,
  isKioskProvisioned,
  isWellFormedPin,
  kioskFontScale,
  kioskReducer,
  pinLockedOut,
  tamperDetected,
  verifyClinicPin,
  type KioskLockdown,
  type KioskProvisioning,
} from "@/lib/kiosk";
import { useSession } from "@/lib/session";
import { scaledSize, spacing } from "@/lib/theme";

export function KioskGate({ children }: { children: ReactNode }) {
  const { setKioskActive, wipeSession } = useSession();
  const [provisioning, setProvisioning] = useState<KioskProvisioning | null>(null);
  const [lockdown, setLockdown] = useState<KioskLockdown>("needs_dev_build");
  const [checked, setChecked] = useState(false);
  const [mode, dispatch] = useReducer(kioskReducer, initialKioskMode);
  const [exiting, setExiting] = useState(false);
  const touchRef = useRef<() => void>(() => {});

  // Read the MDM provisioning and probe the lockdown once, through the lazy
  // native adapter (both fail closed in the managed runtime).
  useEffect(() => {
    let mounted = true;
    void import("@/lib/kiosk/nativeKiosk")
      .then(async (native) => {
        const [prov, lock] = await Promise.all([
          native.readKioskProvisioning(),
          native.probeLockdown(),
        ]);
        if (!mounted) {
          return;
        }
        setProvisioning(prov);
        setLockdown(lock);
        setChecked(true);
      })
      .catch(() => {
        if (mounted) {
          setChecked(true);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const provisioned = isKioskProvisioned(provisioning);

  // The armed patient session is exactly what the session treats as kiosk
  // mode: no persistence, and wipeable between patients.
  useEffect(() => {
    setKioskActive(provisioned && mode.phase === "armed");
  }, [provisioned, mode.phase, setKioskActive]);

  // Leaving the armed phase closes any in-progress staff exit prompt.
  useEffect(() => {
    if (mode.phase !== "armed") {
      setExiting(false);
    }
  }, [mode.phase]);

  // While armed, watch the two wipe triggers. onBackground both wipes AND
  // flags a tamper: a locked-down kiosk should not be backgroundable, so
  // leaving the foreground means the lockdown is no longer trustworthy.
  useEffect(() => {
    if (!provisioned || mode.phase !== "armed") {
      return;
    }
    let watch: { touch(): void; stop(): void } | null = null;
    void import("@/lib/kiosk/nativeKiosk")
      .then((native) => {
        watch = native.watchKiosk({
          onIdle: () => wipeSession(),
          onBackground: () => {
            wipeSession();
            dispatch({ type: "tamper" });
          },
        });
        touchRef.current = () => watch?.touch();
      })
      .catch(() => {});
    return () => {
      watch?.stop();
      touchRef.current = () => {};
    };
  }, [provisioned, mode.phase, wipeSession]);

  const submitArm = useCallback(
    (pin: string) => {
      // Arming re-probes the lockdown and requires it: a kiosk session may not
      // start on a device that is not actually locked down, so a correct PIN
      // alone is not enough (fail closed).
      void import("@/lib/kiosk/nativeKiosk")
        .then(async (native) => {
          const lock = await native.probeLockdown();
          setLockdown(lock);
          dispatch({
            type: "arm",
            pinOk: verifyClinicPin(pin, provisioning) && !tamperDetected(lock),
          });
        })
        .catch(() => {});
    },
    [provisioning],
  );

  const submitDisarm = useCallback(
    (pin: string) => {
      dispatch({ type: "disarm", pinOk: verifyClinicPin(pin, provisioning) });
    },
    [provisioning],
  );

  const submitRecover = useCallback(
    (pin: string) => {
      void import("@/lib/kiosk/nativeKiosk")
        .then(async (native) => {
          const lock = await native.probeLockdown();
          setLockdown(lock);
          dispatch({
            type: "recover",
            pinOk: verifyClinicPin(pin, provisioning),
            lockdownOk: !tamperDetected(lock),
          });
        })
        .catch(() => {});
    },
    [provisioning],
  );

  // Normal phone, or not yet known: render the app untouched.
  if (!checked || !provisioned) {
    return <>{children}</>;
  }

  if (mode.phase === "armed" && !exiting) {
    return (
      <View style={styles.armedRoot} onTouchStart={() => touchRef.current()}>
        <View style={styles.armedContent}>{children}</View>
        <View style={styles.staffBar}>
          <SecondaryButton
            label={t("kiosk.exit")}
            hint={t("kiosk.exitHint")}
            onPress={() => setExiting(true)}
          />
        </View>
      </View>
    );
  }

  if (mode.phase === "armed" && exiting) {
    return (
      <KioskPinScreen
        titleKey="kiosk.exit.title"
        bodyKey="kiosk.exit.body"
        submitKey="kiosk.pin.disarm"
        onSubmit={submitDisarm}
        pinFailures={mode.pinFailures}
        lockedOut={pinLockedOut(mode)}
      />
    );
  }

  if (mode.phase === "tampered") {
    return (
      <KioskPinScreen
        titleKey="kiosk.tamper.title"
        bodyKey="kiosk.tamper.body"
        submitKey="kiosk.pin.recover"
        onSubmit={submitRecover}
        pinFailures={mode.pinFailures}
        lockedOut={pinLockedOut(mode)}
        tamper
      />
    );
  }

  // phase "off": the resting large-type privacy screen — staff arm with the
  // PIN. If the device is not actually locked down, the same banner warns why
  // arming will be refused (fail closed, no silent degrade).
  return (
    <KioskPinScreen
      titleKey="kiosk.lock.title"
      bodyKey="kiosk.lock.body"
      submitKey="kiosk.pin.arm"
      onSubmit={submitArm}
      pinFailures={mode.pinFailures}
      lockedOut={pinLockedOut(mode)}
      tamper={tamperDetected(lockdown)}
      privacyNote
    />
  );
}

interface PinScreenProps {
  titleKey: "kiosk.lock.title" | "kiosk.tamper.title" | "kiosk.exit.title";
  bodyKey: "kiosk.lock.body" | "kiosk.tamper.body" | "kiosk.exit.body";
  submitKey: "kiosk.pin.arm" | "kiosk.pin.disarm" | "kiosk.pin.recover";
  onSubmit: (pin: string) => void;
  pinFailures: number;
  lockedOut: boolean;
  tamper?: boolean;
  privacyNote?: boolean;
}

/**
 * The large-type PIN surface, shared by arm / recover / disarm. It floors at
 * the large-text scale (`kioskFontScale`) for a device read at arm's length,
 * blocks screen capture (privacy on a shared device), and holds the entered
 * PIN only transiently — it is cleared on submit and never stored.
 */
function KioskPinScreen({
  titleKey,
  bodyKey,
  submitKey,
  onSubmit,
  pinFailures,
  lockedOut,
  tamper = false,
  privacyNote = false,
}: PinScreenProps) {
  useClinicalScreenPrivacy();
  const theme = useTheme();
  const scale = kioskFontScale(useFontScale());
  const [pin, setPin] = useState("");
  const [malformed, setMalformed] = useState(false);

  const submit = useCallback(() => {
    if (!isWellFormedPin(pin)) {
      setMalformed(true);
      return;
    }
    setMalformed(false);
    onSubmit(pin);
    setPin("");
  }, [pin, onSubmit]);

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.body}>
        {tamper ? (
          <AppText role="title" color="amber" heading live="assertive">
            {t("kiosk.tamper.banner")}
          </AppText>
        ) : null}
        <AppText role="hero" heading>
          {t(titleKey)}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t(bodyKey)}
        </AppText>
        <TextInput
          accessibilityLabel={t("kiosk.pin.label")}
          accessibilityHint={t("kiosk.pin.hint")}
          // The field applies scaledSize itself, so the OS multiplier is off
          // (SC 1.4.4); the kiosk floor keeps it large on a shared device.
          allowFontScaling={false}
          value={pin}
          onChangeText={(next) => {
            setPin(next);
            setMalformed(false);
          }}
          editable={!lockedOut}
          keyboardType="number-pad"
          secureTextEntry
          style={[
            styles.field,
            {
              backgroundColor: theme.surface,
              borderColor: theme.border,
              color: theme.ink,
              fontSize: scaledSize("title", scale),
            },
          ]}
        />
        {lockedOut ? (
          <AppText role="body" color="amber" live="assertive">
            {t("kiosk.pin.lockedOut")}
          </AppText>
        ) : pinFailures > 0 || malformed ? (
          <AppText role="body" color="amber" live="assertive">
            {t("kiosk.pin.wrong")}
          </AppText>
        ) : null}
        <PrimaryButton
          label={t(submitKey)}
          hint={t("kiosk.pin.submitHint")}
          onPress={submit}
          disabled={lockedOut}
        />
        {privacyNote ? (
          <AppText role="body" color="inkFaint">
            {t("kiosk.privacy.note")}
          </AppText>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  // flexGrow, never flex: centred while it fits, scrolled once it does not
  // (INT-284; the large-text step makes this screen tall).
  body: { flexGrow: 1, justifyContent: "center", gap: spacing.md },
  field: {
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  armedRoot: { flex: 1 },
  armedContent: { flex: 1 },
  staffBar: { padding: spacing.md },
});
