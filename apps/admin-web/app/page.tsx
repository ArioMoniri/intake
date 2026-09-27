/**
 * The console root. Two modules are rendered pages today — the overview
 * (INT-181: SLOs, probes, dependency health) and the ops console (INT-351) —
 * and the overview is the landing page files/08 §3 lists first. The other
 * modules are view-models awaiting their pages, so the root sends an operator
 * to one that exists rather than listing links to nothing.
 */
import { redirect } from "next/navigation";

export default function Home(): never {
  redirect("/overview");
}
