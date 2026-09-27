package intake.keycloak.webauthn;

import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.authenticators.browser.WebAuthnAuthenticator;
import org.keycloak.models.KeycloakSession;

/**
 * Keycloak's stock WebAuthn authenticator, unchanged, plus the two session notes.
 *
 * <p>The hook point is the end of {@code action}: {@code DefaultAuthenticationFlow.processAction}
 * calls {@code authenticator.action(result)} and only then reads {@code result.getStatus()} in
 * {@code processResult}, so notes written after {@code super.action} returns are on the
 * authentication session before the flow moves on (Keycloak 26.1.4,
 * services/.../authentication/DefaultAuthenticationFlow.java).
 */
public final class WebAuthnSessionNotesAuthenticator extends WebAuthnAuthenticator {

  public WebAuthnSessionNotesAuthenticator(KeycloakSession session) {
    super(session);
  }

  @Override
  public void action(AuthenticationFlowContext context) {
    super.action(context);
    WebAuthnSessionNotes.recordAfterAction(context, getCredentialType());
  }
}
