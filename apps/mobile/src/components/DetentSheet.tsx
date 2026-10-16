/**
 * The in-tree detent sheet (ADR-038 A3, INT-473).
 *
 * A sheet with detents is a React view rendered inside the screen that opens
 * it, and so inside the navigator container. It is never a React Native
 * `Modal`, an expo-router `formSheet` or `modal` presentation, or a portal into
 * another window (e2e/sheets.spec.ts). The RED root layer mounts after the
 * navigator container (ADR-033 §5), so it paints above any open sheet, and RED
 * never waits for one.
 *
 * - Two detents, medium and large, and a grabber. Dragging the grabber or the
 *   header follows the finger; a release settles where the throw points, or
 *   closes past the threshold (lib/motion/sheet).
 * - It presents, settles and falls away on A1's critically damped spring
 *   (lib/motion/native/sheetMotion). A privacy or RED close is instant: the
 *   commit that closes it hides the sheet and registers no exit, and the next
 *   commit unmounts it (INT-551). Reanimated reads an exit when a view mounts
 *   or updates, never when it unmounts, so unmounting in the closing commit
 *   would play the patient's spring that the open sheet registered.
 * - Reduce Motion: a 120 ms fade on presenting, an instant close, and a
 *   release that snaps to its detent.
 * - Focus stays inside (`accessibilityViewIsModal`). The VoiceOver escape
 *   gesture and Android's back button close it, as the backdrop does.
 *
 * The sheet's frame is its parent's box: `top` says where the screen's own
 * bar ends inside it, so the large detent stops under the bar rather than
 * under the native header's buttons.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { BackHandler, PanResponder, Pressable, ScrollView, StyleSheet, View } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTheme } from "@/components/Themed";
import { useReducedMotion } from "@/lib/a11y/prefs";
import { MIN_TAP } from "@/lib/a11y/target";
import { sheetEntering, sheetExiting, settleTo } from "@/lib/motion/native/sheetMotion";
import {
  detentOffsets,
  isTap,
  nextDetent,
  settleTarget,
  sheetClose,
  sheetMount,
  sheetPresent,
  sheetSettle,
  type Detent,
  type SheetCloseReason,
  type SheetMount,
} from "@/lib/motion/sheet";
import { radius, spacing } from "@/lib/theme";

interface DetentSheetProps {
  visible: boolean;
  /** Where the screen's own bar ends inside the sheet's frame, in points. */
  top: number;
  /** The patient's own close: the backdrop, a drag, the escape, back. */
  onClose: () => void;
  /** The backdrop's spoken name and what it does. */
  closeLabel: string;
  closeHint: string;
  /**
   * Why the sheet will close next. A privacy or RED close is instant at every
   * setting (lib/motion/sheet); the patient's own close settles.
   */
  closeReason?: SheetCloseReason;
  /** The drag area's content under the grabber: the sheet's title row. */
  header: ReactNode;
  children: ReactNode;
}

export function DetentSheet({
  visible,
  top,
  onClose,
  closeLabel,
  closeHint,
  closeReason = "patient",
  header,
  children,
}: DetentSheetProps) {
  const theme = useTheme();
  const reduce = useReducedMotion();
  const insets = useSafeAreaInsets();
  // The frame is measured, never assumed: a screen under a solid bar starts
  // below it, one under a transparent bar at the top of the window.
  const [height, setHeight] = useState<number | null>(null);
  const offsets = useMemo(() => detentOffsets({ height: height ?? 0, top }), [height, top]);
  const [detent, setDetent] = useState<Detent>("medium");
  const position = useSharedValue(0);
  const dragStart = useRef(0);
  // INT-551: what the last commit drew, so an instant close can take its one
  // hidden commit before the unmount (lib/motion/sheet `sheetMount`). The
  // layout effect stores it, which renders the parked sheet once more, gone.
  const [drawn, setDrawn] = useState<SheetMount>("closed");
  const mount = sheetMount(drawn, {
    visible: visible && height !== null,
    close: sheetClose(closeReason, { reduce }),
  });
  useLayoutEffect(() => {
    if (mount !== drawn) {
      setDrawn(mount);
    }
  }, [mount, drawn]);

  // Every opening starts at the medium detent, placed before the first paint.
  useLayoutEffect(() => {
    if (visible && height !== null) {
      position.set(offsets.medium);
      setDetent("medium");
    }
  }, [visible, height, offsets.medium, position]);

  // Android's back button closes the sheet before it leaves the screen.
  useEffect(() => {
    if (!visible) {
      return undefined;
    }
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      onClose();
      return true;
    });
    return () => subscription.remove();
  }, [visible, onClose]);

  const close = () => onClose();

  const pan = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dy) > 2,
        onPanResponderGrant: () => {
          dragStart.current = position.get();
        },
        // Direct manipulation: the sheet's edge is the finger, never past the
        // large detent and never below the frame.
        onPanResponderMove: (_, gesture) => {
          const frame = height ?? 0;
          position.set(Math.min(frame, Math.max(offsets.large, dragStart.current + gesture.dy)));
        },
        onPanResponderRelease: (_, gesture) => {
          // A tap moves to the other detent: the drag's single-pointer
          // alternative (SC 2.5.7).
          if (isTap(gesture)) {
            const other = nextDetent(detent);
            setDetent(other);
            settleTo(position, offsets[other], sheetSettle({ reduce }));
            return;
          }
          const target = settleTarget({
            offsets,
            height: height ?? 0,
            y: dragStart.current + gesture.dy,
            velocity: gesture.vy,
          });
          if (target === "closed") {
            onClose();
            return;
          }
          setDetent(target);
          settleTo(position, offsets[target], sheetSettle({ reduce }));
        },
      }),
    [detent, height, offsets, onClose, position, reduce],
  );

  const placed = useAnimatedStyle(() => ({ transform: [{ translateY: position.get() }] }));

  if (height === null || mount === "closed") {
    return (
      <View
        pointerEvents="none"
        style={StyleSheet.absoluteFill}
        onLayout={(event) => setHeight(event.nativeEvent.layout.height)}
      />
    );
  }

  // Parked: mounted for this one commit so the update registers the close's
  // own exit, which is none; hidden from sight, touch and assistive technology.
  const parked = mount === "parked";
  return (
    <View
      pointerEvents={parked ? "none" : "auto"}
      style={StyleSheet.absoluteFill}
      onLayout={(event) => setHeight(event.nativeEvent.layout.height)}
    >
      {parked ? null : (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={closeLabel}
          accessibilityHint={closeHint}
          onPress={close}
          style={[StyleSheet.absoluteFill, styles.backdrop]}
        />
      )}
      <Animated.View
        style={[StyleSheet.absoluteFill, parked ? styles.parked : null]}
        pointerEvents="box-none"
        entering={sheetEntering(sheetPresent({ reduce }), height)}
        exiting={sheetExiting(sheetClose(closeReason, { reduce }), height)}
      >
        <Animated.View
          accessibilityViewIsModal
          onAccessibilityEscape={() => close()}
          style={[
            styles.sheet,
            placed,
            {
              height: height - offsets.large,
              backgroundColor: theme.background,
              paddingLeft: insets.left,
              paddingRight: insets.right,
              paddingBottom: insets.bottom,
            },
          ]}
        >
          <View {...pan.panHandlers} style={styles.dragArea}>
            {/* The grabber: the sheet's affordance to the eye. Decoration
                for a screen reader, which closes the sheet by its escape
                gesture or the header's own control. */}
            <View
              accessibilityElementsHidden
              importantForAccessibility="no-hide-descendants"
              style={[styles.grabber, { backgroundColor: theme.inkFaint }]}
            />
            {header}
          </View>
          <ScrollView
            contentContainerStyle={[
              styles.content,
              // At the medium detent the sheet's lower part is below the
              // frame, so the content keeps that much room to scroll into.
              {
                paddingBottom:
                  (detent === "medium" ? offsets.medium - offsets.large : 0) + spacing.xl,
              },
            ]}
          >
            {children}
          </ScrollView>
        </Animated.View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  // The dim behind the sheet; its floor is declared, not inherited (SC 2.5.8).
  backdrop: { backgroundColor: "rgba(0, 0, 0, 0.4)", minHeight: MIN_TAP },
  // The one commit an instant close keeps the sheet for (INT-551).
  parked: { display: "none" },
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    top: 0,
    borderTopLeftRadius: radius.card,
    borderTopRightRadius: radius.card,
    borderCurve: "continuous",
    overflow: "hidden",
  },
  dragArea: { paddingTop: spacing.sm, minHeight: MIN_TAP },
  grabber: {
    alignSelf: "center",
    width: 36,
    height: 5,
    borderRadius: radius.chip,
    marginBottom: spacing.sm,
  },
  content: { paddingHorizontal: spacing.screen },
});
