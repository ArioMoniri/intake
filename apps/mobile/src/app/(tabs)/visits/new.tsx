/**
 * Yeni vizit (02 §4, INT-134): visit creation on the production taxonomy.
 *
 * Two paths, one form. The patient either pastes their MHRS appointment
 * message — parsed on the device, the raw text discarded the moment it is
 * read — or fills the same fields by hand: hospital, a branch from the
 * taxonomy feed (search, common branches first), a visit type the branch
 * actually books, and an optional date.
 *
 * The picker is fed by the server's versioned taxonomy feed, falls back to
 * the last-good cached feed, and finally to the bundled seed, so it is
 * never empty. Screenshot OCR is wired but fail-closed (see
 * `ocrImportAvailable`) — the OCR layer has no verified licence yet
 * (files/03 §4.9.2(f)), and a fake reader would be worse than none.
 */
import { Stack, useRouter } from "expo-router";
import { useEffect, useMemo, useReducer, useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import {
  AppText,
  Card,
  PrimaryButton,
  Screen,
  SecondaryButton,
  useFontScale,
  useStackHeader,
  useTheme,
} from "@/components/Themed";
import { joinParts, labelled } from "@/lib/a11y/labels";
import { useLiveAnnouncement } from "@/lib/a11y/prefs";
import { verticalSlop } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { branchById, intakeBranches, visibleBranches } from "@/lib/taxonomy/branches";
import type { VisitTypeId } from "@/lib/taxonomy/branches";
import { cachedTaxonomy, loadTaxonomy } from "@/lib/taxonomy/client";
import { visitTypeLabelKey } from "@/lib/taxonomy/labels";
import { parseMhrsSms } from "@/lib/taxonomy/mhrsSms";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";
import {
  emptyNewVisitForm,
  formToInput,
  newVisitFormReducer,
  ocrImportAvailable,
  validateNewVisit,
} from "@/lib/visits";

/** Browsing cap: the common ten plus a hint that there is more behind search. */
const BROWSE_LIMIT = 12;

const NOTICE_KEYS = {
  filled: "visits.new.smsFilled",
  unknown_branch: "visits.new.smsUnknownBranch",
  no_date: "visits.new.smsNoDate",
  unreadable: "visits.new.smsUnreadable",
} as const;

export default function NewVisit() {
  const router = useRouter();
  const theme = useTheme();
  const headerOptions = useStackHeader();
  const fontScale = useFontScale();
  const { addVisit, consents } = useSession();
  const [form, dispatch] = useReducer(newVisitFormReducer, undefined, emptyNewVisitForm);
  const [taxonomy, setTaxonomy] = useState(cachedTaxonomy);
  const [query, setQuery] = useState("");
  const [picking, setPicking] = useState(true);

  useEffect(() => {
    let live = true;
    void loadTaxonomy().then((resolved) => {
      if (live) {
        setTaxonomy(resolved);
      }
    });
    return () => {
      live = false;
    };
  }, []);

  // One string, used for the visible line and (prefixed) for the spoken one.
  const problemText =
    form.problem === null
      ? null
      : form.problem === "missing_fields"
        ? t("visits.new.missingFields")
        : t("visits.new.badDate");
  // Android hears the live region on the line; this is the iOS half.
  useLiveAnnouncement(problemText === null ? null : labelled(t("a11y.error"), problemText));

  const bookable = useMemo(() => intakeBranches(taxonomy.branches, taxonomy.clusters), [taxonomy]);
  const shown = useMemo(() => visibleBranches(bookable, query, BROWSE_LIMIT), [bookable, query]);
  const chosen = form.branchId === null ? undefined : branchById(bookable, form.branchId);
  const ocrOffered = ocrImportAvailable(consents);

  const fieldStyle = [
    styles.field,
    {
      backgroundColor: theme.surface,
      borderColor: theme.border,
      color: theme.ink,
      fontSize: scaledSize("body", fontScale),
    },
  ];

  const readSms = () => {
    dispatch({
      type: "apply_sms",
      parsed: parseMhrsSms(form.sms, bookable),
      branches: bookable,
    });
    setPicking(true);
  };

  const save = () => {
    const input = formToInput(form);
    const check = validateNewVisit(input);
    if (!check.ok) {
      dispatch({ type: "set_problem", problem: check.reason });
      return;
    }
    const visit = addVisit(input);
    router.replace(`/(tabs)/visits/${visit.id}`);
  };

  return (
    <Screen edges={["left", "right"]}>
      <Stack.Screen options={headerOptions(t("visits.new.title"))} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AppText role="caption" color="inkFaint">
          {t("visits.new.hint")}
        </AppText>

        {/* --- MHRS message paste-parse --------------------------------- */}
        <Card>
          <Kicker label={t("visits.new.smsTitle")} />
          <AppText role="caption" color="inkFaint">
            {t("visits.new.smsHint")}
          </AppText>
          <TextInput
            accessibilityLabel={t("visits.new.smsTitle")}
            accessibilityHint={t("visits.new.smsHint")}
            allowFontScaling={false}
            value={form.sms}
            onChangeText={(value) => dispatch({ type: "set_sms", value })}
            multiline
            style={[...fieldStyle, styles.smsField]}
          />
          <SecondaryButton
            label={t("visits.new.smsAction")}
            onPress={readSms}
            disabled={form.sms.trim().length === 0}
          />
          {form.smsNotice !== null ? (
            <AppText
              role="body"
              color={form.smsNotice === "filled" ? "inkSoft" : "amber"}
              // The paste either filled the form or did not; either way the
              // result appears above the fields the patient is looking at
              // (SC 3.3.1).
              live="assertive"
            >
              {t(NOTICE_KEYS[form.smsNotice])}
            </AppText>
          ) : null}
          {!ocrOffered ? (
            <AppText role="caption" color="inkFaint">
              {t("visits.new.ocrUnavailable")}
            </AppText>
          ) : null}
        </Card>

        {/* --- the manual fields ---------------------------------------- */}
        <Card>
          <AppText role="label" color="inkSoft">
            {t("visits.new.hospital")}
          </AppText>
          <TextInput
            accessibilityLabel={t("visits.new.hospital")}
            allowFontScaling={false}
            value={form.hospital}
            onChangeText={(value) => dispatch({ type: "set_hospital", value })}
            style={fieldStyle}
          />

          <AppText role="label" color="inkSoft">
            {t("visits.new.branch")}
          </AppText>
          {chosen !== undefined && !picking ? (
            <View style={styles.chosenRow}>
              <AppText role="body">{chosen.nameTr}</AppText>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t("visits.new.branchChange")}
                hitSlop={verticalSlop(18)}
                onPress={() => setPicking(true)}
              >
                <AppText role="caption" color="primary">
                  {t("visits.new.branchChange")}
                </AppText>
              </Pressable>
            </View>
          ) : (
            <>
              {/* A visible caption rather than an in-field hint: a hint that
                  vanishes on focus is unreadable to the low-literacy path
                  (02 §3), and the tab-bar rule bans that token anyway. */}
              <AppText role="caption" color="inkFaint">
                {t("visits.new.branchSearch")}
              </AppText>
              <TextInput
                accessibilityLabel={t("visits.new.branchSearch")}
                allowFontScaling={false}
                value={query}
                onChangeText={setQuery}
                style={fieldStyle}
              />
              <View style={styles.branchList}>
                {shown.map((branch) => (
                  <Pressable
                    key={branch.id}
                    // One branch per visit: the wash marks the chosen one
                    // and a radio is what says so out loud (SC 1.4.1).
                    accessibilityRole="radio"
                    accessibilityLabel={branch.nameTr}
                    accessibilityState={{
                      selected: branch.id === form.branchId,
                      checked: branch.id === form.branchId,
                    }}
                    onPress={() => {
                      dispatch({ type: "pick_branch", branch });
                      setPicking(false);
                      setQuery("");
                    }}
                    style={[
                      styles.branchRow,
                      {
                        backgroundColor:
                          branch.id === form.branchId ? theme.primarySoft : theme.surface,
                        borderColor: theme.border,
                      },
                    ]}
                  >
                    <AppText role="body">{branch.nameTr}</AppText>
                  </Pressable>
                ))}
              </View>
              {query.trim().length === 0 && bookable.length > shown.length ? (
                <AppText role="caption" color="inkFaint">
                  {t("visits.new.branchMore")}
                </AppText>
              ) : null}
            </>
          )}

          {chosen !== undefined ? (
            <>
              <AppText role="label" color="inkSoft">
                {t("visits.new.visitType")}
              </AppText>
              <View style={styles.typeGrid}>
                {chosen.visitTypes.map((visitType: VisitTypeId) => (
                  <Pressable
                    key={visitType}
                    accessibilityRole="radio"
                    accessibilityLabel={t(visitTypeLabelKey(visitType))}
                    accessibilityState={{
                      selected: visitType === form.visitType,
                      checked: visitType === form.visitType,
                    }}
                    onPress={() => dispatch({ type: "pick_visit_type", visitType })}
                    style={[
                      styles.typeChip,
                      {
                        backgroundColor:
                          visitType === form.visitType ? theme.primarySoft : theme.surface,
                        borderColor: theme.border,
                      },
                    ]}
                  >
                    <AppText role="caption">{t(visitTypeLabelKey(visitType))}</AppText>
                  </Pressable>
                ))}
              </View>
            </>
          ) : null}

          <AppText role="label" color="inkSoft">
            {t("visits.new.date")}
          </AppText>
          <TextInput
            accessibilityLabel={t("visits.new.date")}
            // The format line and the "optional" line are instructions ABOUT
            // this field; a sighted patient reads them under it, a screen
            // reader gets them here (SC 3.3.2).
            accessibilityHint={joinParts(t("visits.new.dateHint"), t("visits.new.dateOptional"))}
            allowFontScaling={false}
            value={form.date ?? ""}
            onChangeText={(value) => dispatch({ type: "set_date", value })}
            keyboardType="numbers-and-punctuation"
            style={fieldStyle}
          />
          <AppText role="caption" color="inkFaint">
            {t("visits.new.dateHint")}
          </AppText>
          <AppText role="caption" color="inkFaint">
            {t("visits.new.dateOptional")}
          </AppText>
        </Card>

        {form.problem !== null ? (
          // Visible copy unchanged; the spoken form carries "Hata".
          <AppText role="body" color="amber" live="assertive">
            {problemText}
          </AppText>
        ) : null}
        <PrimaryButton label={t("visits.new.save")} onPress={save} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: TAB_BAR_CLEARANCE },
  field: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontFamily: fonts.sans,
  },
  smsField: { minHeight: 96, textAlignVertical: "top" },
  chosenRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  branchList: { gap: spacing.xs },
  branchRow: {
    borderRadius: radius.control,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  typeGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  typeChip: {
    borderRadius: radius.control,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
});
