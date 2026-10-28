/**
 * INT-563 (ADR-043) — `/step-up`: one pending action and its **Onayla**
 * button, for the second keys no module page lists (break-glass, the access
 * review's countersignature — docs/runbooks/four-eyes-step-up.md), and where a
 * step-up outcome lands when its action has no page.
 *
 * A server component with nothing to load: the action id is shown only when
 * it is id-shaped, and `?step_up=` only when it is one of the step-up codes.
 * Whether the caller may approve is the API's to decide, at the step-up and
 * again at the approve route.
 */
import type { ReactElement } from "react";

import { langFrom } from "../../src/ops/copy";
import { StepUpPage } from "../../src/step-up/form";
import { stepUpResultFrom } from "../../src/step-up/results";

export default async function StepUp({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const params = await searchParams;
  const actionId = params["action_id"];
  return (
    <StepUpPage
      actionId={typeof actionId === "string" ? actionId : null}
      result={stepUpResultFrom(params["step_up"])}
      lang={langFrom(params["lang"])}
    />
  );
}
