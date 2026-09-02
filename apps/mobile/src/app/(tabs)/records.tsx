/**
 * Kayıtlarım (02 §4, real since INT-229): patient-owned documents over the
 * INT-197 endpoints. Gated on the documents consent scope; dev-tier
 * accounts keep their honest fixture list (no faked uploads); OTP accounts
 * upload real files (expo-document-picker limited to the server allow-list),
 * see worded scan-state chips — colour never the only carrier (02 §8.2) —
 * and open clean documents through expo-web-browser. Design pass 5 anatomy:
 * ListGroup rows, guidance blocks instead of dead ends.
 */
import * as DocumentPicker from "expo-document-picker";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, RAIL_EDGES, Screen, SecondaryButton, useTheme } from "@/components/Themed";
import { formatVisitDate } from "@/components/VisitCard";
import { joinParts, labelled } from "@/lib/a11y/labels";
import { useLiveAnnouncement } from "@/lib/a11y/prefs";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { getLocale, t, type MessageKey } from "@/lib/i18n";
import {
  ALLOWED_DOCUMENT_TYPES,
  RecordsApiError,
  docDisplayName,
  downloadUrl,
  ensureServerVisit,
  listDocuments,
  pickUploadVisit,
  precheckFile,
  rememberDocName,
  upload,
  type RecordDoc,
  type ScanState,
} from "@/lib/records/api";
import { useSession, type RecordFixture, type VisitFixture } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

/** Scan state is always a WORD (02 §8.2) — the chip colour only echoes it. */
const SCAN_STATE_KEY: Record<ScanState, MessageKey> = {
  quarantined: "records.state.scanning",
  clean: "records.state.ready",
  rejected: "records.state.rejected",
};

function ScanChip({ state }: { state: ScanState }) {
  const theme = useTheme();
  const colors = {
    quarantined: { bg: theme.surfaceRaised, fg: theme.inkSoft },
    clean: { bg: theme.successSoft, fg: theme.success },
    rejected: { bg: theme.surfaceRaised, fg: theme.ink },
  }[state];
  return (
    <View style={[styles.chip, { backgroundColor: colors.bg }]}>
      <AppText role="caption" style={{ color: colors.fg, fontWeight: "600" }}>
        {t(SCAN_STATE_KEY[state])}
      </AppText>
    </View>
  );
}

function errorKey(error: unknown): MessageKey {
  if (error instanceof RecordsApiError) {
    switch (error.kind) {
      case "type":
        return "records.err.type";
      case "size":
        return "records.err.size";
      case "network":
        return "records.err.network";
      case "session":
        return "records.err.session";
      case "consent":
        return "records.err.consent";
      case "scan_unavailable":
        return "records.err.scanUnavailable";
      default:
        return "records.err.generic";
    }
  }
  return "records.err.generic";
}

/**
 * Dev-tier accounts are session-local fixtures with no server identity —
 * the list stays the honest synthetic sample and upload simply is not
 * offered (never a faked upload).
 */
function DevRecords({ records }: { records: readonly RecordFixture[] }) {
  return (
    <>
      {records.length === 0 ? (
        <GuidanceBlock
          accent
          icon="folder"
          kickerKey="records.guide.kicker"
          titleKey="records.guide.title"
          bodyKey="records.guide.body"
        />
      ) : (
        <View style={styles.section}>
          <Kicker label={t("records.guide.kicker")} />
          <ListGroup footer={t("records.synthetic")}>
            {records.map((record) => (
              <ListRow
                key={record.id}
                icon="doc.text"
                label={record.title}
                sublabel={formatVisitDate(record.date, getLocale())}
              />
            ))}
          </ListGroup>
        </View>
      )}
      <AppText role="caption" color="inkFaint">
        {t("records.devNote")}
      </AppText>
    </>
  );
}

type Phase = "loading" | "ready" | "offline";

function OtpRecords() {
  const router = useRouter();
  const { visits } = useSession();
  const todayIso = new Date().toISOString().slice(0, 10);
  const pick = pickUploadVisit(visits, todayIso);

  const [chosen, setChosen] = useState<VisitFixture | null>(null);
  const selected = chosen ?? (pick.kind === "one" ? pick.visit : null);

  const [phase, setPhase] = useState<Phase>("loading");
  const [serverVisitId, setServerVisitId] = useState<string | null>(null);
  const [docs, setDocs] = useState<RecordDoc[]>([]);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<MessageKey | null>(null);
  const noticeIsError = notice !== null && notice !== "records.scanningInfo";
  // Android hears the live region on the line; this is the iOS half.
  useLiveAnnouncement(
    notice === null ? null : noticeIsError ? labelled(t("a11y.error"), t(notice)) : t(notice),
  );

  const refresh = useCallback(async (visit: VisitFixture) => {
    setPhase("loading");
    setNotice(null);
    try {
      // read-only resolve: listing must never create the server visit
      const visitId = await ensureServerVisit(visit, { create: false });
      setServerVisitId(visitId);
      setDocs(visitId === null ? [] : await listDocuments(visitId));
      setPhase("ready");
    } catch (error) {
      if (error instanceof RecordsApiError && error.kind === "network") {
        setPhase("offline");
        return;
      }
      setPhase("ready");
      setDocs([]);
      setNotice(errorKey(error));
    }
  }, []);

  useEffect(() => {
    if (selected !== null) {
      void refresh(selected);
    }
  }, [selected, refresh]);

  const onUpload = useCallback(async () => {
    if (selected === null) {
      return;
    }
    setNotice(null);
    const picked = await DocumentPicker.getDocumentAsync({
      type: [...ALLOWED_DOCUMENT_TYPES],
      copyToCacheDirectory: true,
      multiple: false,
    });
    if (picked.canceled) {
      return;
    }
    const asset = picked.assets[0];
    const pre = precheckFile(asset);
    if (!pre.ok) {
      setNotice(pre.reason === "type" ? "records.err.type" : "records.err.size");
      return;
    }
    setUploading(true);
    try {
      const visitId = serverVisitId ?? (await ensureServerVisit(selected, { create: true }));
      if (visitId === null) {
        setNotice("records.err.generic");
        return;
      }
      setServerVisitId(visitId);
      const outcome = await upload(visitId, asset);
      // the patient's own filename, kept on device only (invariant 6)
      rememberDocName(outcome.id, asset.name);
      if (outcome.state === "rejected") {
        setNotice("records.err.rejected");
      }
      setDocs(await listDocuments(visitId));
      setPhase("ready");
    } catch (error) {
      setNotice(errorKey(error));
    } finally {
      setUploading(false);
    }
  }, [selected, serverVisitId]);

  const onOpen = useCallback(
    async (doc: RecordDoc) => {
      if (doc.state === "quarantined") {
        setNotice("records.scanningInfo");
        return;
      }
      if (doc.state !== "clean" || serverVisitId === null) {
        return;
      }
      try {
        const result = await downloadUrl(serverVisitId, doc.id);
        if (result.kind === "scanning") {
          setNotice("records.scanningInfo");
          return;
        }
        await WebBrowser.openBrowserAsync(result.url);
      } catch (error) {
        setNotice(errorKey(error));
      }
    },
    [serverVisitId],
  );

  if (pick.kind === "none") {
    return (
      <>
        <GuidanceBlock
          accent
          icon="calendar"
          kickerKey="records.needVisit.kicker"
          titleKey="records.needVisit.title"
          bodyKey="records.needVisit.body"
        />
        <SecondaryButton
          label={t("today.addVisit")}
          onPress={() => router.push("/(tabs)/visits/new")}
        />
      </>
    );
  }

  if (selected === null && pick.kind === "choose") {
    return (
      <View style={styles.section}>
        <Kicker label={t("records.visit.kicker")} />
        <AppText role="body" color="inkSoft">
          {t("records.visit.choose")}
        </AppText>
        <ListGroup>
          {pick.visits.map((visit) => (
            <ListRow
              key={visit.id}
              icon="calendar"
              label={visit.hospital}
              sublabel={joinParts(visit.department, formatVisitDate(visit.date, getLocale()))}
              chevron
              hint={t("a11y.openHint")}
              onPress={() => setChosen(visit)}
            />
          ))}
        </ListGroup>
      </View>
    );
  }

  if (selected === null) {
    return null; // unreachable: "one" always selects — kept for the type
  }

  if (phase === "offline") {
    return (
      <>
        <GuidanceBlock
          icon="wifi.slash"
          kickerKey="records.offline.kicker"
          titleKey="records.offline.title"
          bodyKey="records.offline.body"
        />
        <SecondaryButton label={t("records.retry")} onPress={() => void refresh(selected)} />
      </>
    );
  }

  return (
    <>
      <View style={styles.section}>
        <Kicker label={t("records.visit.kicker")} />
        <ListGroup>
          <ListRow
            icon="calendar"
            label={selected.hospital}
            sublabel={joinParts(selected.department, formatVisitDate(selected.date, getLocale()))}
            chevron={pick.kind === "choose"}
            hint={pick.kind === "choose" ? t("a11y.openHint") : undefined}
            onPress={pick.kind === "choose" ? () => setChosen(null) : undefined}
          />
        </ListGroup>
      </View>
      {phase === "ready" && docs.length === 0 ? (
        <GuidanceBlock
          accent
          icon="folder"
          kickerKey="records.guide.kicker"
          titleKey="records.guide.title"
          bodyKey="records.guide.body"
        />
      ) : null}
      {docs.length > 0 ? (
        <View style={styles.section}>
          <Kicker label={t("records.guide.kicker")} />
          <ListGroup>
            {docs.map((doc) => (
              <ListRow
                key={doc.id}
                icon={doc.contentType === "application/pdf" ? "doc.text" : "photo"}
                label={
                  docDisplayName(doc.id) ??
                  t(doc.contentType === "application/pdf" ? "records.doc.pdf" : "records.doc.image")
                }
                sublabel={formatVisitDate(doc.createdAt.slice(0, 10), getLocale())}
                // The scan state is a word in the trailing chip, but a
                // pressed row merges its subtree — so the state is repeated
                // into the row's own name or it is lost (SC 4.1.2).
                labelContext={t(SCAN_STATE_KEY[doc.state])}
                trailing={<ScanChip state={doc.state} />}
                hint={doc.state === "rejected" ? undefined : t("a11y.openHint")}
                onPress={doc.state === "rejected" ? undefined : () => void onOpen(doc)}
              />
            ))}
          </ListGroup>
        </View>
      ) : null}
      {notice !== null ? (
        // SC 3.3.1. `notice` is not always an error: "records.scanningInfo"
        // is a progress line, so only the error kinds are prefixed "Hata"
        // and announced assertively — dressing a scan-in-progress message as
        // an error would be worse than not announcing it. Visible copy is
        // unchanged either way.
        <AppText role="body" color="amber" live={noticeIsError ? "assertive" : "polite"}>
          {t(notice)}
        </AppText>
      ) : null}
      <SecondaryButton
        label={uploading ? t("records.uploading") : t("records.upload")}
        onPress={() => void onUpload()}
        disabled={uploading || phase === "loading"}
      />
    </>
  );
}

export default function Records() {
  useClinicalScreenPrivacy(); // clinical screen: FLAG_SECURE-class (INT-131)
  const router = useRouter();
  const { account, consents } = useSession();
  const documentsAllowed = consents?.documents === true;
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: useTabBarClearance() }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("records.title")}
        </AppText>
        {!documentsAllowed ? (
          <>
            <GuidanceBlock
              accent
              icon="checkmark.shield"
              kickerKey="records.consent.kicker"
              titleKey="records.consent.title"
              bodyKey="records.consent.body"
            />
            <SecondaryButton
              label={t("records.consent.cta")}
              onPress={() => router.push("/(tabs)/me/consents")}
            />
          </>
        ) : account?.kind === "otp" ? (
          <OtpRecords />
        ) : (
          <DevRecords records={account?.records ?? []} />
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl },
  heroLine: { marginTop: spacing.xl },
  section: { gap: spacing.sm },
  chip: {
    alignSelf: "center",
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
});
