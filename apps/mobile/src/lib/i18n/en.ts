import type { MessageKey } from "./tr";

/** English mirrors — every key must exist in tr first (tr is the source of
 * truth; the i18n test enforces key parity). */
export const en: Record<MessageKey, string> = {
  "app.name": "Vizite",
  "app.tagline": "What you tell us reaches your doctor before the visit.",
  "app.disclaimer":
    "Vizite does not diagnose. What you share never replaces your doctor's assessment.",

  "tabs.today": "Today",
  "tabs.visits": "My visits",
  "tabs.records": "My records",
  "tabs.wellbeing": "Wellbeing",
  "tabs.me": "Profile",

  "welcome.title": "Welcome",
  "welcome.body":
    "Vizite collects your complaints by voice or text before the visit and hands your doctor a structured pre-visit note.",
  "welcome.devSignIn": "Sign in with a test account",
  "welcome.devNote":
    "This screen exists only in development builds; real sign-in uses phone verification.",

  "today.nextVisit": "Next visit",
  "today.prepareCta": "Prepare for the visit (≈3 min)",
  "today.continueCta": "Continue",
  "today.noVisit": "No visit scheduled.",
  "today.addVisit": "Add a visit",
  "today.uploadQuick": "Upload a record",

  "status.draft": "Draft",
  "status.sent": "Sent",
  "status.viewed": "Viewed by doctor",
  "status.filed": "Added to file",

  "visits.title": "My visits",
  "visits.upcoming": "Upcoming",
  "visits.past": "Past",
  "visits.empty": "You have not added a visit yet.",
  "visits.new.title": "New visit",
  "visits.new.manual": "Add manually",
  "visits.new.hint": "Enter hospital, department and date; adding from an MHRS message is coming.",
  "visits.detail.summary": "Summary",
  "visits.detail.noteStatus": "Note status",
  "visits.detail.notStarted": "The conversation has not started yet.",

  "records.title": "My records",
  "records.empty": "No records yet. You can add lab results and reports before your visit.",
  "records.synthetic": "Sample data — synthetic",

  "wellbeing.title": "Wellbeing",
  "wellbeing.intro": "Track how you feel; sharing stays under your control.",
  "wellbeing.empty": "No entries yet.",

  "me.title": "Profile",
  "me.consents": "Your consents",
  "me.language": "Language",
  "me.learned": "What it learned about me",
  "me.learnedEmpty":
    "Vizite never permanently learns anything about you without your confirmation.",
  "me.signOut": "Sign out",
  "me.syntheticBadge": "Synthetic test account",

  "consent.core": "Core service",
  "consent.voice": "Voice sessions",
  "consent.wellbeing": "Wellbeing screening",
  "consent.documents": "Document upload",
  "consent.on": "On",
  "consent.off": "Off",
};
