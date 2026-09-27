package intake.keycloak.webauthn;

import static intake.keycloak.webauthn.Fixtures.AAGUID_A;
import static intake.keycloak.webauthn.Fixtures.ID_A;
import static intake.keycloak.webauthn.Fixtures.base64Url;
import static intake.keycloak.webauthn.Fixtures.stored;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.webauthn4j.util.exception.WebAuthnException;
import org.junit.jupiter.api.Test;
import org.keycloak.WebAuthnConstants;
import org.keycloak.authentication.FlowStatus;
import org.keycloak.authentication.authenticators.browser.WebAuthnAuthenticator;
import org.keycloak.credential.CredentialInput;
import org.mockito.InOrder;

/**
 * The authenticator runs Keycloak 26.1.4's own WebAuthnAuthenticator.action unchanged. Only the
 * assertion check at its core (SubjectCredentialManager.isValid, which webauthn4j backs) is
 * stubbed, so each test decides whether the stock code accepts the assertion; everything the stock
 * action does around it runs for real.
 */
class WebAuthnSessionNotesAuthenticatorTest {

  @Test
  void itIsTheStockAuthenticator() {
    Fixtures.Flow flow = new Fixtures.Flow();
    assertInstanceOf(
        WebAuthnAuthenticator.class, new WebAuthnSessionNotesAuthenticator(flow.session));
  }

  @Test
  void aStockSuccessWritesBothNotesAfterTheStockActionSucceeded() {
    Fixtures.Flow flow =
        new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).withStockActionInputs(ID_A);
    when(flow.credentials.isValid(any(CredentialInput.class))).thenReturn(true);

    new WebAuthnSessionNotesAuthenticator(flow.session).action(flow.context);

    assertEquals(FlowStatus.SUCCESS, flow.status.value);
    InOrder order = inOrder(flow.context, flow.authSession);
    order.verify(flow.context).success();
    order.verify(flow.authSession).setUserSessionNote(WebAuthnSessionNotes.AAGUID_NOTE, AAGUID_A);
    order
        .verify(flow.authSession)
        .setUserSessionNote(WebAuthnSessionNotes.CREDENTIAL_ID_NOTE, base64Url(ID_A));
    // the stock event detail carries the same credential id the note does
    verify(flow.event).detail(WebAuthnConstants.PUBKEY_CRED_ID_ATTR, base64Url(ID_A));
  }

  @Test
  void aStockRejectionWritesNothing() {
    // near-miss control for the test above: the stock check says no, all else equal
    Fixtures.Flow flow =
        new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).withStockActionInputs(ID_A);
    when(flow.credentials.isValid(any(CredentialInput.class))).thenReturn(false);

    new WebAuthnSessionNotesAuthenticator(flow.session).action(flow.context);

    assertEquals(FlowStatus.FAILED, flow.status.value);
    verify(flow.context).cancelLogin();
    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @Test
  void aVerificationFailureWritesNothing() {
    Fixtures.Flow flow =
        new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).withStockActionInputs(ID_A);
    when(flow.credentials.isValid(any(CredentialInput.class)))
        .thenThrow(new WebAuthnException("signature does not verify"));

    new WebAuthnSessionNotesAuthenticator(flow.session).action(flow.context);

    assertEquals(FlowStatus.FAILED, flow.status.value);
    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @Test
  void anErrorFromTheBrowserWritesNothing() {
    Fixtures.Flow flow =
        new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).withStockActionInputs(ID_A);
    flow.params.putSingle(WebAuthnConstants.ERROR, "NotAllowedError");
    when(flow.credentials.isValid(any(CredentialInput.class))).thenReturn(true);

    new WebAuthnSessionNotesAuthenticator(flow.session).action(flow.context);

    assertEquals(FlowStatus.FAILED, flow.status.value);
    verify(flow.credentials, never()).isValid(any(CredentialInput.class));
    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }
}
