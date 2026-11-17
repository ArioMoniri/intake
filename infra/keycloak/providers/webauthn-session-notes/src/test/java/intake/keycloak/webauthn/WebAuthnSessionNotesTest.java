package intake.keycloak.webauthn;

import static intake.keycloak.webauthn.Fixtures.AAGUID_A;
import static intake.keycloak.webauthn.Fixtures.AAGUID_B;
import static intake.keycloak.webauthn.Fixtures.ID_A;
import static intake.keycloak.webauthn.Fixtures.ID_B;
import static intake.keycloak.webauthn.Fixtures.PADDED_ID;
import static intake.keycloak.webauthn.Fixtures.base64Url;
import static intake.keycloak.webauthn.Fixtures.stored;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import java.util.EnumSet;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.keycloak.WebAuthnConstants;
import org.keycloak.authentication.FlowStatus;
import org.keycloak.models.credential.WebAuthnCredentialModel;

/**
 * The note logic alone: what is written after the stock action has run, given the status it left.
 */
class WebAuthnSessionNotesTest {

  private static final String TYPE = WebAuthnCredentialModel.TYPE_TWOFACTOR;

  @Test
  void theNoteNamesAreTheOnesTheRealmMappersRead() {
    // infra/keycloak/dev-realm.json, admin-web mappers "aaguid" and "credential_id" (INT-373)
    assertEquals("intake.webauthn.aaguid", WebAuthnSessionNotes.AAGUID_NOTE);
    assertEquals("intake.webauthn.credential_id", WebAuthnSessionNotes.CREDENTIAL_ID_NOTE);
  }

  @Test
  void afterASuccessBothNotesAreWrittenAndNothingElse() {
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).asserting(ID_A);
    flow.status.value = FlowStatus.SUCCESS;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession).setUserSessionNote(WebAuthnSessionNotes.AAGUID_NOTE, AAGUID_A);
    verify(flow.authSession)
        .setUserSessionNote(WebAuthnSessionNotes.CREDENTIAL_ID_NOTE, base64Url(ID_A));
    verifyNoMoreInteractions(flow.authSession);
  }

  @Test
  void theCredentialIdIsBase64UrlWithoutPaddingNotTheStoredStandardBase64() {
    // stored as "+/+/AQ==" (standard Base64); the note is the unpadded base64url form, the
    // form the stock authenticator puts in its event detail and on its login page
    Fixtures.Flow flow =
        new Fixtures.Flow().storing(stored(AAGUID_A, PADDED_ID)).asserting(PADDED_ID);
    flow.status.value = FlowStatus.SUCCESS;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession).setUserSessionNote(WebAuthnSessionNotes.CREDENTIAL_ID_NOTE, "-_-_AQ");
  }

  @Test
  void theAaguidComesFromTheAssertedCredentialNotTheFirstOneStored() {
    Fixtures.Flow flow =
        new Fixtures.Flow()
            .storing(stored(AAGUID_A, ID_A), stored(AAGUID_B, ID_B))
            .asserting(ID_B);
    flow.status.value = FlowStatus.SUCCESS;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession).setUserSessionNote(WebAuthnSessionNotes.AAGUID_NOTE, AAGUID_B);
    verify(flow.authSession)
        .setUserSessionNote(WebAuthnSessionNotes.CREDENTIAL_ID_NOTE, base64Url(ID_B));
    verifyNoMoreInteractions(flow.authSession);
  }

  @Test
  void nearMissTheSameFlowWithAnotherStatusWritesNothing() {
    // the control for the test above: one field differs
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).asserting(ID_A);
    flow.status.value = FlowStatus.FAILED;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  static Stream<FlowStatus> everyStatusButSuccess() {
    return Stream.concat(
        EnumSet.complementOf(EnumSet.of(FlowStatus.SUCCESS)).stream(), Stream.of((FlowStatus) null));
  }

  @ParameterizedTest
  @MethodSource("everyStatusButSuccess")
  void nothingIsWrittenUnlessTheStockActionSucceeded(FlowStatus status) {
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).asserting(ID_A);
    flow.status.value = status;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @Test
  void nothingIsWrittenWhenNoStoredCredentialHasTheAssertedId() {
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).asserting(ID_B);
    flow.status.value = FlowStatus.SUCCESS;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @Test
  void onlyCredentialsOfTheAuthenticatorsOwnTypeAreConsidered() {
    // a passwordless credential with the same id is not the two-factor one that was asserted
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).asserting(ID_A);
    flow.status.value = FlowStatus.SUCCESS;

    WebAuthnSessionNotes.recordAfterAction(
        flow.context, WebAuthnCredentialModel.TYPE_PASSWORDLESS);

    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @Test
  void nothingIsWrittenWithoutAnAuthenticatedUser() {
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(AAGUID_A, ID_A)).asserting(ID_A);
    flow.status.value = FlowStatus.SUCCESS;
    when(flow.context.getUser()).thenReturn(null);

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @ParameterizedTest
  @NullAndEmptySource
  void nothingIsWrittenWhenTheStoredAaguidIsMissing(String aaguid) {
    // both notes or neither: a credential id without its AAGUID is not written alone
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(aaguid, ID_A)).asserting(ID_A);
    flow.status.value = FlowStatus.SUCCESS;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }

  @ParameterizedTest
  @NullAndEmptySource
  void nothingIsWrittenWhenTheAssertedIdIsMissing(String asserted) {
    Fixtures.Flow flow = new Fixtures.Flow().storing(stored(AAGUID_A, ID_A));
    if (asserted != null) {
      flow.params.putSingle(WebAuthnConstants.CREDENTIAL_ID, asserted);
    }
    flow.status.value = FlowStatus.SUCCESS;

    WebAuthnSessionNotes.recordAfterAction(flow.context, TYPE);

    verify(flow.authSession, never()).setUserSessionNote(anyString(), anyString());
  }
}
