/** Entry: route to the shell when signed in, welcome otherwise. */
import { Redirect } from "expo-router";

import { useSession } from "@/lib/session";

// scroll-exempt(redirect): this route renders no content of its own — it hands
// the patient straight to the shell or to welcome, and there is nothing on it
// that a larger text size could push out of reach.
export default function Index() {
  const { account } = useSession();
  return account ? <Redirect href="/(tabs)/today" /> : <Redirect href="/(auth)/welcome" />;
}
