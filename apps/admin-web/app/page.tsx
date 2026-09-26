/**
 * The console root. The ops page is the one rendered module today (INT-351);
 * the other modules are view-models awaiting their pages, so the root sends
 * an operator to the one that exists rather than listing links to nothing.
 */
import { redirect } from "next/navigation";

export default function Home(): never {
  redirect("/ops");
}
