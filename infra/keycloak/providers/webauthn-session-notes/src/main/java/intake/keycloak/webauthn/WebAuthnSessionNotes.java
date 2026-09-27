package intake.keycloak.webauthn;

import java.io.IOException;
import java.util.Arrays;
import java.util.Optional;
import org.keycloak.WebAuthnConstants;
import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.FlowStatus;
import org.keycloak.common.util.Base64;
import org.keycloak.common.util.Base64Url;
import org.keycloak.models.UserModel;
import org.keycloak.models.credential.WebAuthnCredentialModel;
import org.keycloak.models.credential.dto.WebAuthnCredentialData;
import org.keycloak.sessions.AuthenticationSessionModel;

/**
 * Writes the two user-session notes the admin console's token needs, after a WebAuthn assertion
 * that Keycloak's own authenticator accepted.
 *
 * <p>Keycloak 26.1.4's {@code WebAuthnAuthenticator.action} verifies the assertion and, on success,
 * records the credential id only as an event detail and calls {@code context.success()}; it writes
 * no note. The notes written here are copied into the user session by {@code
 * TokenManager.attachAuthenticationSession}, and the realm's {@code
 * oidc-usersessionmodel-note-mapper}s emit them as the {@code aaguid} and {@code credential_id}
 * claims (docs/runbooks/keycloak-realm.md §3).
 *
 * <p>Both values are identifiers of the authenticator and the credential, never of the person: the
 * AAGUID names the authenticator model, and the credential id is the random id the authenticator
 * minted at registration. Nothing is logged.
 */
public final class WebAuthnSessionNotes {

  /** Read by the admin-web mapper {@code aaguid} (infra/keycloak/dev-realm.json). */
  public static final String AAGUID_NOTE = "intake.webauthn.aaguid";

  /** Read by the admin-web mapper {@code credential_id} (infra/keycloak/dev-realm.json). */
  public static final String CREDENTIAL_ID_NOTE = "intake.webauthn.credential_id";

  private WebAuthnSessionNotes() {}

  /**
   * Called once the stock action has returned. Writes both notes only if that action ended in
   * {@link FlowStatus#SUCCESS} and the asserted credential id is the id of one stored credential of
   * {@code credentialType} belonging to the authenticated user, and that credential has an AAGUID.
   * Otherwise it writes nothing: the token then lacks both claims and the console refuses it.
   *
   * <p>The asserted id is read from the same form parameter, and decoded the same way, as the stock
   * action reads it; the stored id is decoded the way {@code
   * WebAuthnCredentialProvider.getCredentialInputFromCredentialModel} decodes it before {@code
   * isValid} compares the two.
   */
  public static void recordAfterAction(AuthenticationFlowContext context, String credentialType) {
    if (context.getStatus() != FlowStatus.SUCCESS) {
      return;
    }
    UserModel user = context.getUser();
    if (user == null) {
      return;
    }
    byte[] asserted =
        decodeBase64Url(
            context
                .getHttpRequest()
                .getDecodedFormParameters()
                .getFirst(WebAuthnConstants.CREDENTIAL_ID));
    if (asserted.length == 0) {
      return;
    }
    Optional<WebAuthnCredentialData> matched =
        user.credentialManager()
            .getStoredCredentialsByTypeStream(credentialType)
            .map(WebAuthnCredentialModel::createFromCredentialModel)
            .map(WebAuthnCredentialModel::getWebAuthnCredentialData)
            .filter(data -> Arrays.equals(decodeBase64(data.getCredentialId()), asserted))
            .findFirst();
    if (matched.isEmpty()) {
      return;
    }
    String aaguid = matched.get().getAaguid();
    if (aaguid == null || aaguid.isEmpty()) {
      return;
    }
    AuthenticationSessionModel authSession = context.getAuthenticationSession();
    authSession.setUserSessionNote(AAGUID_NOTE, aaguid);
    authSession.setUserSessionNote(CREDENTIAL_ID_NOTE, Base64Url.encode(asserted));
  }

  private static byte[] decodeBase64Url(String value) {
    if (value == null || value.isEmpty()) {
      return new byte[0];
    }
    try {
      return Base64Url.decode(value);
    } catch (RuntimeException malformed) {
      return new byte[0];
    }
  }

  private static byte[] decodeBase64(String value) {
    if (value == null || value.isEmpty()) {
      return new byte[0];
    }
    try {
      return Base64.decode(value);
    } catch (IOException | RuntimeException malformed) {
      return new byte[0];
    }
  }
}
