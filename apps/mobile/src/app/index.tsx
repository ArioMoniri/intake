/** Entry: route to the shell when signed in, welcome otherwise. */
import { Redirect } from "expo-router";

import { useSession } from "@/lib/session";

export default function Index() {
  const { account, hydrated } = useSession();
  // Wait for the one-shot session restore (INT-131) before deciding: routing on
  // the initial `account === null` would send a restoring patient to welcome
  // and never come back once this route unmounts.
  if (!hydrated) {
    return null;
  }
  return account ? <Redirect href="/(tabs)/today" /> : <Redirect href="/(auth)/welcome" />;
}
