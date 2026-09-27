package intake.keycloak.webauthn;

import org.keycloak.authentication.Authenticator;
import org.keycloak.authentication.authenticators.browser.WebAuthnAuthenticatorFactory;
import org.keycloak.models.KeycloakSession;

/**
 * Registers {@link WebAuthnSessionNotesAuthenticator} under its own id. Everything else (reference
 * category, requirement choices, user setup, the WEB_AUTHN feature check) is the stock factory's.
 * The realm's staff browser flow names this id in place of {@code webauthn-authenticator}.
 */
public final class WebAuthnSessionNotesAuthenticatorFactory extends WebAuthnAuthenticatorFactory {

  public static final String PROVIDER_ID = "intake-webauthn-session-notes";

  @Override
  public String getId() {
    return PROVIDER_ID;
  }

  @Override
  public String getDisplayType() {
    return "WebAuthn Authenticator (INTAKE session notes)";
  }

  @Override
  public String getHelpText() {
    return "The stock WebAuthn authenticator. After a successful assertion it also writes the"
        + " credential's AAGUID and its base64url id as the user-session notes"
        + " intake.webauthn.aaguid and intake.webauthn.credential_id.";
  }

  @Override
  public Authenticator create(KeycloakSession session) {
    return new WebAuthnSessionNotesAuthenticator(session);
  }
}
