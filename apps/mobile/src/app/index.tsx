/** Entry: route to the shell when signed in, welcome otherwise. */
import { Redirect } from "expo-router";

import { useSession } from "@/lib/session";

export default function Index() {
  const { account } = useSession();
  return account ? <Redirect href="/(tabs)/today" /> : <Redirect href="/(auth)/welcome" />;
}
