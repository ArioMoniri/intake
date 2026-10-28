package intake.keycloak.webauthn;

import static intake.keycloak.webauthn.Fixtures.AAGUID_A;
import static intake.keycloak.webauthn.Fixtures.ID_A;
import static intake.keycloak.webauthn.Fixtures.base64Url;
import static intake.keycloak.webauthn.Fixtures.stored;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.webauthn4j.util.exception.WebAuthnException;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.keycloak.WebAuthnConstants;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.authentication.FlowStatus;
import org.keycloak.authentication.RequiredActionFactory;
import org.keycloak.authentication.RequiredActionProvider;
import org.keycloak.authentication.authenticators.browser.WebAuthnAuthenticator;
import org.keycloak.authentication.requiredactions.WebAuthnRegisterFactory;
import org.keycloak.credential.CredentialInput;
import org.keycloak.models.KeycloakContext;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.RequiredActionProviderModel;
import org.keycloak.models.credential.OTPCredentialModel;
import org.keycloak.models.credential.WebAuthnCredentialModel;
import org.mockito.InOrder;

/**
 * The authenticator runs Keycloak 26.7.4's own WebAuthnAuthenticator.action unchanged. Only the
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

  // --- INT-550: what Keycloak's flow engine asks before it sends a user to registration --------

  @Test
  void itNeedsTheUserThePasswordStepIdentified() {
    Fixtures.Flow flow = new Fixtures.Flow();
    assertTrue(new WebAuthnSessionNotesAuthenticator(flow.session).requiresUser());
  }

  @Test
  void itIsConfiguredOnlyForAUserWithAPasskey() {
    Fixtures.Flow flow = new Fixtures.Flow();
    WebAuthnSessionNotesAuthenticator authenticator =
        new WebAuthnSessionNotesAuthenticator(flow.session);
    when(flow.credentials.isConfiguredFor(anyString())).thenReturn(false);
    // near miss: an OTP (or any other) credential does not count
    when(flow.credentials.isConfiguredFor(OTPCredentialModel.TYPE)).thenReturn(true);
    assertFalse(authenticator.configuredFor(flow.session, flow.realm, flow.user));

    when(flow.credentials.isConfiguredFor(WebAuthnCredentialModel.TYPE_TWOFACTOR)).thenReturn(true);
    assertTrue(authenticator.configuredFor(flow.session, flow.realm, flow.user));
  }

  @Test
  void setupAsksForWebauthnRegisterOnce() {
    Fixtures.Flow flow = new Fixtures.Flow();
    Set<String> asked = new LinkedHashSet<>();
    KeycloakContext keycloakContext = mock(KeycloakContext.class);
    when(flow.session.getContext()).thenReturn(keycloakContext);
    when(keycloakContext.getAuthenticationSession()).thenReturn(flow.authSession);
    when(flow.authSession.getRequiredActions()).thenAnswer(invocation -> Set.copyOf(asked));
    doAnswer(invocation -> asked.add(invocation.getArgument(0)))
        .when(flow.authSession)
        .addRequiredAction(anyString());
    WebAuthnSessionNotesAuthenticator authenticator =
        new WebAuthnSessionNotesAuthenticator(flow.session);

    authenticator.setRequiredActions(flow.session, flow.realm, flow.user);
    authenticator.setRequiredActions(flow.session, flow.realm, flow.user);

    assertEquals(Set.of(WebAuthnRegisterFactory.PROVIDER_ID), asked);
    verify(flow.authSession).addRequiredAction(WebAuthnRegisterFactory.PROVIDER_ID);
  }

  @Test
  void setupNeedsTheRealmsWebauthnRegisterActionEnabled() {
    Fixtures.Flow flow = new Fixtures.Flow();
    KeycloakSessionFactory sessionFactory = mock(KeycloakSessionFactory.class);
    when(flow.session.getKeycloakSessionFactory()).thenReturn(sessionFactory);
    when(sessionFactory.getProviderFactory(RequiredActionProvider.class, "webauthn-register"))
        .thenReturn(new WebAuthnRegisterFactory());
    WebAuthnSessionNotesAuthenticator authenticator =
        new WebAuthnSessionNotesAuthenticator(flow.session);
    RequiredActionProviderModel register = new RequiredActionProviderModel();
    register.setAlias("webauthn-register");
    register.setEnabled(true);
    when(flow.realm.getRequiredActionProviderByAlias("webauthn-register")).thenReturn(register);

    assertEquals(
        List.of("webauthn-register"),
        authenticator.getRequiredActions(flow.session).stream()
            .map(RequiredActionFactory::getId)
            .toList());
    assertTrue(authenticator.areRequiredActionsEnabled(flow.session, flow.realm));

    // near misses: the action disabled, or absent from the realm
    register.setEnabled(false);
    assertFalse(authenticator.areRequiredActionsEnabled(flow.session, flow.realm));
    when(flow.realm.getRequiredActionProviderByAlias("webauthn-register")).thenReturn(null);
    assertFalse(authenticator.areRequiredActionsEnabled(flow.session, flow.realm));
  }

  @Test
  void aStockSuccessWritesBothNotesAfterTheStockActionSucceeded() {
    Fixtures.Flow flow =
        new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).withStockActionInputs(ID_A);
    when(flow.credentials.isValid(any(CredentialInput.class))).thenReturn(true);

    new WebAuthnSessionNotesAuthenticator(flow.session).action(flow.context);

    assertEquals(FlowStatus.SUCCESS, flow.status.value);
    InOrder order = inOrder(flow.context, flow.authSession);
    order.verify(flow.context).success(WebAuthnCredentialModel.TYPE_TWOFACTOR);
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
    // 26.7.4 answers a rejected assertion as an unknown user and no longer cancels the login
    // (it named which accounts exist); either way the flow fails and no note is written
    verify(flow.context).failure(eq(AuthenticationFlowError.UNKNOWN_USER), any());
    verify(flow.context, never()).cancelLogin();
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
