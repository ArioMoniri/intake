package intake.keycloak.webauthn;

import static intake.keycloak.webauthn.FlowEngine.OTP_FORM;
import static intake.keycloak.webauthn.FlowEngine.WEBAUTHN_REGISTER;
import static intake.keycloak.webauthn.WebAuthnSessionNotesAuthenticatorFactory.PROVIDER_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.keycloak.authentication.AuthenticationFlow;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.authentication.AuthenticationFlowException;
import org.keycloak.authentication.AuthenticationSelectionOption;
import org.keycloak.models.AuthenticationExecutionModel.Requirement;
import org.keycloak.models.Constants;
import org.keycloak.sessions.CommonClientSessionModel.ExecutionStatus;
import org.mockito.ArgumentCaptor;

/**
 * INT-550: once the password step has identified a staff user who holds no passkey, the realm's
 * browser flow sends them to the webauthn-register required action instead of refusing them, and
 * OTP is no way around WebAuthn.
 *
 * <p>Keycloak 26.7.4's own flow engine runs the browser flow with the second-factor subflow both
 * committed realms carry (FlowEngine). For a user without the credential, the engine marks an
 * execution SETUP_REQUIRED and asks for its required action only when the execution is REQUIRED,
 * its factory allows user setup, and the action is enabled in the realm
 * (DefaultAuthenticationFlow.processSingleFlowExecutionModel). Otherwise it records
 * CREDENTIAL_SETUP_REQUIRED, the flow ends unsuccessful, and the login page says "Invalid username
 * or password". That is what the synthetic host showed on 17 Oct 2026.
 */
class StaffSecondFactorFlowTest {

  /** The live subflow on the host, 17 Oct 2026: WebAuthn and OTP as two ALTERNATIVEs. */
  private static final List<FlowEngine.Step> HOSTS_SHAPE =
      List.of(
          new FlowEngine.Step(PROVIDER_ID, Requirement.ALTERNATIVE, 10),
          new FlowEngine.Step(OTP_FORM, Requirement.ALTERNATIVE, 20));

  @Test
  void aNewUserIsSentToPasskeyRegistrationAfterThePassword() {
    FlowEngine engine = new FlowEngine(FlowEngine.committedSecondFactor());
    AuthenticationFlow login = engine.login();

    assertNull(login.processFlow());

    // the flow completes; Keycloak then runs the required action before issuing a code
    assertTrue(login.isSuccessful());
    assertEquals(
        ExecutionStatus.SETUP_REQUIRED,
        engine.statuses.get(engine.secondFactorExecution(PROVIDER_ID).getId()));
    assertEquals(Set.of(WEBAUTHN_REGISTER), engine.requiredActions);
    assertFalse(engine.authenticatorsAsked.contains(OTP_FORM));
    // nothing asserted a passkey in this login, so WebAuthn is not a completed execution and
    // this login's amr is the password's alone: the console refuses that token, and the next
    // fresh sign-in asserts the new passkey (tests/admin/test_staff_passkey_enrolment.py)
    verify(engine.authSession, never())
        .setUserSessionNote(eq(Constants.AUTHENTICATORS_COMPLETED), anyString());
  }

  @Test
  void aUserWithAPasskeyIsChallengedForItAndCannotSkipIt() {
    FlowEngine engine = new FlowEngine(FlowEngine.committedSecondFactor()).holdingPasskey();
    AuthenticationFlow login = engine.login();

    assertSame(engine.webAuthnPage, login.processFlow());

    assertFalse(login.isSuccessful());
    assertEquals(
        ExecutionStatus.CHALLENGED,
        engine.statuses.get(engine.secondFactorExecution(PROVIDER_ID).getId()));
    assertEquals(List.of(PROVIDER_ID), offered(engine));
    assertTrue(engine.requiredActions.isEmpty());
  }

  @Test
  void theNextSignInAssertsTheNewPasskeyAndCompletesWithBothNotes() {
    // a fresh login after enrolment: the password, then the WebAuthn page posted back
    FlowEngine engine =
        new FlowEngine(FlowEngine.committedSecondFactor()).holdingPasskey().presentingPasskey(true);
    AuthenticationFlow login = engine.login();
    String webauthn = engine.secondFactorExecution(PROVIDER_ID).getId();

    assertNull(engine.submitPasskey(login));

    assertTrue(login.isSuccessful());
    assertEquals(ExecutionStatus.SUCCESS, engine.statuses.get(webauthn));
    // WebAuthn is a completed execution now (the amr mapper's hwk), and the provider wrote both
    // notes the console requires (INT-378)
    verify(engine.authSession)
        .setUserSessionNote(eq(Constants.AUTHENTICATORS_COMPLETED), contains(webauthn));
    verify(engine.authSession)
        .setUserSessionNote(WebAuthnSessionNotes.AAGUID_NOTE, Fixtures.AAGUID_A);
    verify(engine.authSession)
        .setUserSessionNote(
            WebAuthnSessionNotes.CREDENTIAL_ID_NOTE, Fixtures.base64Url(Fixtures.ID_A));
    assertTrue(engine.requiredActions.isEmpty());
  }

  @Test
  void otpIsNotOfferedToAUserWhoHoldsBoth() {
    FlowEngine engine =
        new FlowEngine(FlowEngine.committedSecondFactor()).holdingPasskey().holdingOtp();

    assertSame(engine.webAuthnPage, engine.login().processFlow());

    assertEquals(List.of(PROVIDER_ID), offered(engine));
    assertFalse(engine.authenticatorsAsked.contains(OTP_FORM));
  }

  @Test
  void otpIsNotAcceptedInPlaceOfThePasskey() {
    FlowEngine engine =
        new FlowEngine(FlowEngine.committedSecondFactor()).holdingPasskey().holdingOtp();

    AuthenticationFlowException refused =
        assertThrows(
            AuthenticationFlowException.class, () -> engine.switchTo(PROVIDER_ID, OTP_FORM));

    assertEquals(AuthenticationFlowError.INTERNAL_ERROR, refused.getError());
    assertEquals("Requested authentication execution is not allowed", refused.getMessage());
    assertFalse(engine.authenticatorsAsked.contains(OTP_FORM));
  }

  @Test
  void anOtpCredentialIsNoWayAroundPasskeyRegistration() {
    FlowEngine engine = new FlowEngine(FlowEngine.committedSecondFactor()).holdingOtp();
    AuthenticationFlow login = engine.login();

    assertNull(login.processFlow());

    assertEquals(
        ExecutionStatus.SETUP_REQUIRED,
        engine.statuses.get(engine.secondFactorExecution(PROVIDER_ID).getId()));
    assertEquals(Set.of(WEBAUTHN_REGISTER), engine.requiredActions);
    assertFalse(engine.authenticatorsAsked.contains(OTP_FORM));
  }

  // --- near misses: each differs from a case above in one thing ------------------------------

  @Test
  void nearMissTheHostsShapeRefusesANewUser() {
    FlowEngine engine = new FlowEngine(HOSTS_SHAPE);
    AuthenticationFlow login = engine.login();

    assertNull(login.processFlow());

    // not successful, with no exception of its own: "Invalid username or password"
    assertFalse(login.isSuccessful());
    assertTrue(login.getFlowExceptions().isEmpty());
    assertEquals(
        List.of(
            AuthenticationFlowError.CREDENTIAL_SETUP_REQUIRED,
            AuthenticationFlowError.CREDENTIAL_SETUP_REQUIRED),
        errors(engine.secondFactorRun()));
    assertTrue(engine.requiredActions.isEmpty());
  }

  @Test
  void nearMissAnAlternativeWebauthnAloneStillRefusesANewUser() {
    // OTP out of the way, but Keycloak never sends an ALTERNATIVE to setup
    FlowEngine engine =
        new FlowEngine(FlowEngine.committedWith(PROVIDER_ID, Requirement.ALTERNATIVE));
    AuthenticationFlow login = engine.login();

    assertNull(login.processFlow());

    assertFalse(login.isSuccessful());
    assertEquals(
        List.of(AuthenticationFlowError.CREDENTIAL_SETUP_REQUIRED),
        errors(engine.secondFactorRun()));
    assertTrue(engine.requiredActions.isEmpty());
  }

  @Test
  void nearMissAnAssertionThatDoesNotVerifyCompletesNothing() {
    FlowEngine engine =
        new FlowEngine(FlowEngine.committedSecondFactor())
            .holdingPasskey()
            .presentingPasskey(false);
    AuthenticationFlow login = engine.login();

    assertSame(engine.webAuthnErrorPage, engine.submitPasskey(login));

    assertFalse(login.isSuccessful());
    assertEquals(
        ExecutionStatus.FAILED,
        engine.statuses.get(engine.secondFactorExecution(PROVIDER_ID).getId()));
    verify(engine.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @Test
  void nearMissTheHostsShapeOffersOtpToAUserWhoHoldsBoth() {
    FlowEngine engine = new FlowEngine(HOSTS_SHAPE).holdingPasskey().holdingOtp();

    assertSame(engine.webAuthnPage, engine.login().processFlow());

    assertEquals(List.of(PROVIDER_ID, OTP_FORM), offered(engine));
  }

  @Test
  void nearMissTheHostsShapeLetsAnOtpCredentialStandInForThePasskey() {
    FlowEngine engine = new FlowEngine(HOSTS_SHAPE).holdingOtp();

    engine.login().processFlow();

    assertTrue(engine.authenticatorsAsked.contains(OTP_FORM));
    assertTrue(engine.requiredActions.isEmpty());
  }

  @Test
  void nearMissADisabledRegisterActionLeavesANewUserNoWayIn() {
    FlowEngine engine = new FlowEngine(FlowEngine.committedSecondFactor());
    engine.register.setEnabled(false);
    AuthenticationFlow login = engine.login();

    assertNull(login.processFlow());

    // a REQUIRED step's exception is not collected below the top flow: the login fails with it
    // (handleBrowserExceptionList, Messages.CREDENTIAL_SETUP_REQUIRED)
    assertFalse(login.isSuccessful());
    assertEquals(List.of(AuthenticationFlowError.CREDENTIAL_SETUP_REQUIRED), errors(login));
    assertTrue(engine.requiredActions.isEmpty());
  }

  private static List<AuthenticationFlowError> errors(AuthenticationFlow flow) {
    return flow.getFlowExceptions().stream()
        .map(AuthenticationFlowException::getError)
        .collect(Collectors.toList());
  }

  /** The executions the engine offered on the authenticator's page ("try another way"). */
  private static List<String> offered(FlowEngine engine) {
    @SuppressWarnings("unchecked")
    ArgumentCaptor<List<AuthenticationSelectionOption>> options =
        ArgumentCaptor.forClass((Class<List<AuthenticationSelectionOption>>) (Class<?>) List.class);
    verify(engine.context, atLeastOnce()).setAuthenticationSelections(options.capture());
    return options.getValue().stream()
        .map(option -> option.getAuthenticationExecution().getAuthenticator())
        .collect(Collectors.toList());
  }
}
