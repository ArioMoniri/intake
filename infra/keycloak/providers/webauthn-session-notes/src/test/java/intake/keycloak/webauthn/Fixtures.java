package intake.keycloak.webauthn;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.RETURNS_SELF;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import jakarta.ws.rs.core.MultivaluedHashMap;
import jakarta.ws.rs.core.MultivaluedMap;
import java.net.URI;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.keycloak.WebAuthnConstants;
import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.authentication.FlowStatus;
import org.keycloak.authentication.authenticators.browser.WebAuthnMetadataService;
import org.keycloak.credential.CredentialModel;
import org.keycloak.credential.CredentialProvider;
import org.keycloak.credential.WebAuthnCredentialProvider;
import org.keycloak.credential.WebAuthnCredentialProviderFactory;
import org.keycloak.events.EventBuilder;
import org.keycloak.forms.login.LoginFormsProvider;
import org.keycloak.http.HttpRequest;
import org.keycloak.models.Constants;
import org.keycloak.models.KeycloakContext;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakUriInfo;
import org.keycloak.models.RealmModel;
import org.keycloak.models.SubjectCredentialManager;
import org.keycloak.models.UserModel;
import org.keycloak.models.UserProvider;
import org.keycloak.models.WebAuthnPolicy;
import org.keycloak.models.credential.WebAuthnCredentialModel;
import org.keycloak.sessions.AuthenticationSessionModel;

/**
 * Synthetic Keycloak objects for the tests. Every id here is made up for the test: the AAGUIDs are
 * random version-4 UUIDs belonging to no authenticator model, and no value is a person's.
 */
final class Fixtures {

  static final String AAGUID_A = "3f1c9a52-7b0e-4d6a-9c1e-5a8b2d4f6e01";
  static final String AAGUID_B = "8d2e4b61-0c3f-4a7e-b5d9-1e6f2a3c4b02";
  static final String USER_ID = "user-0001";

  /** A credential id whose standard Base64 carries '+', '/' and '=' padding. */
  static final byte[] PADDED_ID = {(byte) 0xfb, (byte) 0xff, (byte) 0xbf, 0x01};

  static final byte[] ID_A = bytes(16, 0x11);
  static final byte[] ID_B = bytes(16, 0x22);

  private Fixtures() {}

  static byte[] bytes(int length, int seed) {
    byte[] out = new byte[length];
    for (int i = 0; i < length; i++) {
      out[i] = (byte) (seed + i);
    }
    return out;
  }

  static String base64Url(byte[] raw) {
    return Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
  }

  /** A stored credential as Keycloak keeps it: the id in standard Base64 (with padding). */
  static CredentialModel stored(String aaguid, byte[] credentialId) {
    WebAuthnCredentialModel model =
        WebAuthnCredentialModel.create(
            WebAuthnCredentialModel.TYPE_TWOFACTOR,
            "synthetic key",
            aaguid,
            Base64.getEncoder().encodeToString(credentialId),
            null,
            "c3ludGhldGljLWNvc2Uta2V5",
            0L,
            "none",
            Set.of());
    model.setId("db-" + base64Url(credentialId));
    model.setCreatedDate(1_790_000_000_000L);
    return model;
  }

  /** Mutable flow status, so a mocked context behaves like AuthenticationProcessor.Result. */
  static final class Status {
    FlowStatus value;
  }

  /** The objects one flow step touches, wired the way Keycloak wires them. */
  static final class Flow {
    final KeycloakSession session = mock(KeycloakSession.class);
    final AuthenticationFlowContext context = mock(AuthenticationFlowContext.class);
    final AuthenticationSessionModel authSession = mock(AuthenticationSessionModel.class);
    final UserModel user = mock(UserModel.class);
    final SubjectCredentialManager credentials = mock(SubjectCredentialManager.class);
    final RealmModel realm = mock(RealmModel.class);
    final HttpRequest request = mock(HttpRequest.class);
    final EventBuilder event = mock(EventBuilder.class, RETURNS_SELF);
    final LoginFormsProvider form = mock(LoginFormsProvider.class, RETURNS_SELF);
    final MultivaluedMap<String, String> params = new MultivaluedHashMap<>();
    final Status status = new Status();
    List<CredentialModel> storedCredentials = List.of();

    Flow() {
      when(context.getSession()).thenReturn(session);
      when(context.getAuthenticationSession()).thenReturn(authSession);
      when(context.getRealm()).thenReturn(realm);
      when(context.getHttpRequest()).thenReturn(request);
      when(context.getEvent()).thenReturn(event);
      when(context.form()).thenReturn(form);
      when(request.getDecodedFormParameters()).thenReturn(params);
      when(context.getUser()).thenReturn(user);
      when(context.getStatus()).thenAnswer(invocation -> status.value);
      doAnswer(invocation -> status.value = FlowStatus.SUCCESS).when(context).success();
      // 26.7.4's stock action names the credential type it succeeded with
      doAnswer(invocation -> status.value = FlowStatus.SUCCESS).when(context).success(anyString());
      doAnswer(invocation -> status.value = FlowStatus.FAILED)
          .when(context)
          .failure(any(AuthenticationFlowError.class), any());
      doAnswer(invocation -> status.value = FlowStatus.FAILED)
          .when(context)
          .failure(any(AuthenticationFlowError.class));
      when(user.getId()).thenReturn(USER_ID);
      when(user.credentialManager()).thenReturn(credentials);
      when(credentials.getStoredCredentialsByTypeStream(anyString()))
          .thenAnswer(
              invocation ->
                  storedCredentials.stream()
                      .filter(c -> c.getType().equals(invocation.getArgument(0))));
    }

    Flow storing(CredentialModel... models) {
      storedCredentials = List.of(models);
      return this;
    }

    Flow asserting(byte[] credentialId) {
      params.putSingle(WebAuthnConstants.CREDENTIAL_ID, base64Url(credentialId));
      return this;
    }

    /** What the stock action needs beyond the note logic: policy, origin, challenge, user lookup. */
    Flow withStockActionInputs(byte[] credentialId) {
      asserting(credentialId);
      params.putSingle(WebAuthnConstants.CLIENT_DATA_JSON, base64Url(bytes(8, 0x31)));
      params.putSingle(WebAuthnConstants.AUTHENTICATOR_DATA, base64Url(bytes(37, 0x41)));
      params.putSingle(WebAuthnConstants.SIGNATURE, base64Url(bytes(8, 0x51)));
      params.putSingle(WebAuthnConstants.USER_HANDLE, "");
      WebAuthnPolicy policy = new WebAuthnPolicy();
      policy.setRpId("kc.example.test");
      policy.setUserVerificationRequirement(Constants.WEBAUTHN_POLICY_OPTION_REQUIRED);
      when(realm.getWebAuthnPolicy()).thenReturn(policy);
      KeycloakUriInfo uriInfo = mock(KeycloakUriInfo.class);
      when(uriInfo.getBaseUri()).thenReturn(URI.create("https://kc.example.test/"));
      when(context.getUriInfo()).thenReturn(uriInfo);
      when(authSession.getAuthNote(WebAuthnConstants.AUTH_CHALLENGE_NOTE))
          .thenReturn(base64Url(bytes(32, 0x61)));
      UserProvider users = mock(UserProvider.class);
      when(session.users()).thenReturn(users);
      when(users.getUserById(realm, USER_ID)).thenReturn(user);
      KeycloakContext keycloakContext = mock(KeycloakContext.class);
      when(session.getContext()).thenReturn(keycloakContext);
      when(keycloakContext.resolveLocale(user)).thenReturn(Locale.ENGLISH);
      // 26.7.4's error page lists the user's authenticators with their metadata
      WebAuthnCredentialProvider credentialProvider = mock(WebAuthnCredentialProvider.class);
      when(credentialProvider.getMetadataService()).thenReturn(mock(WebAuthnMetadataService.class));
      when(session.getProvider(CredentialProvider.class, WebAuthnCredentialProviderFactory.PROVIDER_ID))
          .thenReturn(credentialProvider);
      return this;
    }
  }
}
