package intake.keycloak.webauthn;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.RETURNS_SELF;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.ws.rs.HttpMethod;
import jakarta.ws.rs.core.MultivaluedHashMap;
import jakarta.ws.rs.core.MultivaluedMap;
import jakarta.ws.rs.core.Response;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.keycloak.WebAuthnConstants;
import org.keycloak.authentication.AuthenticationFlow;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.authentication.AuthenticationProcessor;
import org.keycloak.authentication.Authenticator;
import org.keycloak.authentication.AuthenticatorFactory;
import org.keycloak.authentication.DefaultAuthenticationFlow;
import org.keycloak.authentication.FlowStatus;
import org.keycloak.authentication.RequiredActionProvider;
import org.keycloak.authentication.authenticators.browser.CookieAuthenticatorFactory;
import org.keycloak.authentication.authenticators.browser.OTPFormAuthenticator;
import org.keycloak.authentication.authenticators.browser.OTPFormAuthenticatorFactory;
import org.keycloak.authentication.authenticators.browser.UsernamePasswordFormFactory;
import org.keycloak.authentication.authenticators.browser.WebAuthnMetadataService;
import org.keycloak.authentication.requiredactions.WebAuthnRegisterFactory;
import org.keycloak.credential.CredentialInput;
import org.keycloak.credential.CredentialModel;
import org.keycloak.credential.CredentialProvider;
import org.keycloak.credential.OTPCredentialProvider;
import org.keycloak.credential.OTPCredentialProviderFactory;
import org.keycloak.credential.WebAuthnCredentialProvider;
import org.keycloak.credential.WebAuthnCredentialProviderFactory;
import org.keycloak.events.EventBuilder;
import org.keycloak.forms.login.LoginFormsProvider;
import org.keycloak.http.HttpRequest;
import org.keycloak.models.AuthenticationExecutionModel;
import org.keycloak.models.AuthenticationExecutionModel.Requirement;
import org.keycloak.models.AuthenticationFlowModel;
import org.keycloak.models.Constants;
import org.keycloak.models.KeycloakContext;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.KeycloakUriInfo;
import org.keycloak.models.RealmModel;
import org.keycloak.models.RequiredActionProviderModel;
import org.keycloak.models.SubjectCredentialManager;
import org.keycloak.models.UserModel;
import org.keycloak.models.UserProvider;
import org.keycloak.models.WebAuthnPolicy;
import org.keycloak.models.credential.OTPCredentialModel;
import org.keycloak.models.credential.WebAuthnCredentialModel;
import org.keycloak.sessions.AuthenticationSessionModel;
import org.keycloak.sessions.CommonClientSessionModel.ExecutionStatus;

/**
 * Keycloak 26.7.4's own {@link DefaultAuthenticationFlow} over the realm's staff browser flow, for
 * one user the password step has already identified.
 *
 * <p>The flow engine, the selection resolver, this module's provider and Keycloak's own OTP form
 * and webauthn-register factories all run unchanged. Only what a running server would hand them
 * is stubbed: the realm's flow and execution lookups, the session and its provider lookups, the
 * authentication session (a real status map and required-action set), and the user's stored
 * credentials. The second-factor subflow is the one both committed realms carry ({@link
 * #committedSecondFactor()}).
 */
final class FlowEngine {

  static final String BROWSER = "flow-staff-browser";
  static final String FORMS = "flow-staff-browser-forms";
  static final String SECOND_FACTOR = "flow-staff-second-factor";
  static final String COOKIE = "auth-cookie";
  static final String PASSWORD_FORM = "auth-username-password-form";
  static final String OTP_FORM = "auth-otp-form";
  static final String WEBAUTHN_REGISTER = "webauthn-register";

  /** One execution of the second-factor subflow, as the realm JSON states it. */
  record Step(String authenticator, Requirement requirement, int priority) {}

  final KeycloakSession session = mock(KeycloakSession.class);
  final KeycloakSessionFactory sessionFactory = mock(KeycloakSessionFactory.class);
  final RealmModel realm = mock(RealmModel.class);
  final AuthenticationProcessor processor = mock(AuthenticationProcessor.class);
  final AuthenticationSessionModel authSession = mock(AuthenticationSessionModel.class);
  final UserModel user = mock(UserModel.class);
  final SubjectCredentialManager credentials = mock(SubjectCredentialManager.class);
  final AuthenticationProcessor.Result context = mock(AuthenticationProcessor.Result.class);
  final LoginFormsProvider form = mock(LoginFormsProvider.class, RETURNS_SELF);
  final Response webAuthnPage = mock(Response.class);
  final Response webAuthnErrorPage = mock(Response.class);
  final HttpRequest request = mock(HttpRequest.class);
  final MultivaluedMap<String, String> formParameters = new MultivaluedHashMap<>();

  final Map<String, ExecutionStatus> statuses = new HashMap<>();
  final Set<String> requiredActions = new LinkedHashSet<>();
  final RequiredActionProviderModel register = new RequiredActionProviderModel();
  final List<String> authenticatorsAsked = new ArrayList<>();
  final List<CredentialModel> stored = new ArrayList<>();

  private final Map<String, AuthenticationFlowModel> flows = new HashMap<>();
  private final Map<String, List<AuthenticationExecutionModel>> executions = new HashMap<>();
  private final Map<String, AuthenticatorFactory> factories = new HashMap<>();
  private final Map<String, AuthenticationFlow> created = new HashMap<>();
  private AuthenticationExecutionModel contextExecution;
  private FlowStatus contextStatus;
  private Response contextChallenge;

  FlowEngine(List<Step> secondFactor) {
    flow(BROWSER, "staff browser", true);
    flow(FORMS, "staff browser forms", false);
    flow(SECOND_FACTOR, "staff second factor", false);
    executions.put(
        BROWSER,
        List.of(
            execution("exec-cookie", BROWSER, COOKIE, Requirement.ALTERNATIVE, 10, null),
            execution("exec-forms", BROWSER, null, Requirement.ALTERNATIVE, 20, FORMS)));
    executions.put(
        FORMS,
        List.of(
            execution("exec-password", FORMS, PASSWORD_FORM, Requirement.REQUIRED, 10, null),
            execution("exec-second-factor", FORMS, null, Requirement.REQUIRED, 20, SECOND_FACTOR)));
    executions.put(
        SECOND_FACTOR,
        secondFactor.stream()
            .sorted(Comparator.comparingInt(Step::priority))
            .map(
                step ->
                    execution(
                        "exec-" + step.authenticator(),
                        SECOND_FACTOR,
                        step.authenticator(),
                        step.requirement(),
                        step.priority(),
                        null))
            .collect(Collectors.toList()));
    // no SSO cookie, and the password form has already identified the user
    statuses.put("exec-cookie", ExecutionStatus.ATTEMPTED);
    statuses.put("exec-password", ExecutionStatus.SUCCESS);

    register.setAlias(WEBAUTHN_REGISTER);
    register.setProviderId(WEBAUTHN_REGISTER);
    register.setEnabled(true);

    wireRealm();
    wireSession();
    wireAuthenticationSession();
    wireUser();
    wireContext();
  }

  /** The second-factor subflow both committed realms carry (src/test/resources). */
  static List<Step> committedSecondFactor() {
    try (InputStream in = FlowEngine.class.getResourceAsStream("/staff-second-factor.json")) {
      if (in == null) {
        throw new IllegalStateException("staff-second-factor.json is not on the test classpath");
      }
      JsonNode root = new ObjectMapper().readTree(in);
      List<Step> steps = new ArrayList<>();
      for (JsonNode node : root.get("authenticationExecutions")) {
        steps.add(
            new Step(
                node.get("authenticator").asText(),
                Requirement.valueOf(node.get("requirement").asText()),
                node.get("priority").asInt()));
      }
      return steps;
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  /** The committed subflow with one execution's requirement changed. */
  static List<Step> committedWith(String authenticator, Requirement requirement) {
    return committedSecondFactor().stream()
        .map(
            step ->
                step.authenticator().equals(authenticator)
                    ? new Step(step.authenticator(), requirement, step.priority())
                    : step)
        .collect(Collectors.toList());
  }

  FlowEngine holdingPasskey() {
    stored.add(Fixtures.stored(Fixtures.AAGUID_A, Fixtures.ID_A));
    return this;
  }

  FlowEngine holdingOtp() {
    OTPCredentialModel otp = OTPCredentialModel.createTOTP("c3ludGhldGlj", 6, 30, "HmacSHA1");
    otp.setId("db-otp-0001");
    stored.add(otp);
    return this;
  }

  /**
   * The form a browser posts back from the WebAuthn page, for the stored passkey. Only the
   * signature check at the core of the stock action (SubjectCredentialManager.isValid, which
   * webauthn4j backs) is stubbed, to {@code verifies}; the rest of the action runs unchanged.
   */
  FlowEngine presentingPasskey(boolean verifies) {
    formParameters.putSingle(WebAuthnConstants.CREDENTIAL_ID, Fixtures.base64Url(Fixtures.ID_A));
    formParameters.putSingle(
        WebAuthnConstants.CLIENT_DATA_JSON, Fixtures.base64Url(Fixtures.bytes(8, 0x31)));
    formParameters.putSingle(
        WebAuthnConstants.AUTHENTICATOR_DATA, Fixtures.base64Url(Fixtures.bytes(37, 0x41)));
    formParameters.putSingle(
        WebAuthnConstants.SIGNATURE, Fixtures.base64Url(Fixtures.bytes(8, 0x51)));
    formParameters.putSingle(WebAuthnConstants.USER_HANDLE, "");
    when(authSession.getAuthNote(WebAuthnConstants.AUTH_CHALLENGE_NOTE))
        .thenReturn(Fixtures.base64Url(Fixtures.bytes(32, 0x61)));
    when(credentials.isValid(any(CredentialInput.class))).thenReturn(verifies);
    return this;
  }

  /** The WebAuthn page's form posted to the login, as the browser does after the assertion. */
  Response submitPasskey(AuthenticationFlow login) {
    return login.processAction(
        secondFactorExecution(WebAuthnSessionNotesAuthenticatorFactory.PROVIDER_ID).getId());
  }

  AuthenticationExecutionModel secondFactorExecution(String authenticator) {
    return executions.get(SECOND_FACTOR).stream()
        .filter(e -> authenticator.equals(e.getAuthenticator()))
        .findFirst()
        .orElseThrow();
  }

  /**
   * The realm's browser flow, top to bottom, as Keycloak evaluates it once the password form has
   * succeeded (the cookie step found no session). AuthenticationProcessor.authenticateOnly then
   * reads {@link AuthenticationFlow#isSuccessful()}: a flow that returns no page and is not
   * successful is thrown as an AuthenticationFlowException carrying {@link
   * AuthenticationFlow#getFlowExceptions()}, and an empty list is shown as "Invalid username or
   * password" (handleBrowserException, Messages.INVALID_USER).
   */
  AuthenticationFlow login() {
    return new DefaultAuthenticationFlow(processor, flows.get(BROWSER));
  }

  /** The second-factor subflow the last {@link #login()} ran, to read its own exceptions. */
  AuthenticationFlow secondFactorRun() {
    return created.get(SECOND_FACTOR);
  }

  /** A POST to the WebAuthn page asking to switch to another execution ("try another way"). */
  Response switchTo(String fromAuthenticator, String toAuthenticator) {
    formParameters.putSingle(
        Constants.AUTHENTICATION_EXECUTION, secondFactorExecution(toAuthenticator).getId());
    return login().processAction(secondFactorExecution(fromAuthenticator).getId());
  }

  private void flow(String id, String alias, boolean topLevel) {
    AuthenticationFlowModel model = new AuthenticationFlowModel();
    model.setId(id);
    model.setAlias(alias);
    model.setProviderId("basic-flow");
    model.setTopLevel(topLevel);
    flows.put(id, model);
  }

  private static AuthenticationExecutionModel execution(
      String id,
      String parent,
      String authenticator,
      Requirement requirement,
      int priority,
      String subflow) {
    AuthenticationExecutionModel model = new AuthenticationExecutionModel();
    model.setId(id);
    model.setParentFlow(parent);
    model.setAuthenticator(authenticator);
    model.setRequirement(requirement);
    model.setPriority(priority);
    model.setAuthenticatorFlow(subflow != null);
    model.setFlowId(subflow);
    return model;
  }

  private List<AuthenticationExecutionModel> all() {
    return executions.values().stream().flatMap(List::stream).collect(Collectors.toList());
  }

  private void wireRealm() {
    when(realm.getAuthenticationExecutionsStream(anyString()))
        .thenAnswer(i -> executions.getOrDefault(i.<String>getArgument(0), List.of()).stream());
    when(realm.getAuthenticationFlowById(anyString()))
        .thenAnswer(i -> flows.get(i.<String>getArgument(0)));
    when(realm.getAuthenticationExecutionByFlowId(anyString()))
        .thenAnswer(
            i ->
                all().stream()
                    .filter(e -> i.<String>getArgument(0).equals(e.getFlowId()))
                    .findFirst()
                    .orElse(null));
    when(realm.getAuthenticationExecutionById(anyString()))
        .thenAnswer(
            i ->
                all().stream()
                    .filter(e -> i.<String>getArgument(0).equals(e.getId()))
                    .findFirst()
                    .orElse(null));
    when(realm.getRequiredActionProviderByAlias(WEBAUTHN_REGISTER)).thenReturn(register);
    WebAuthnPolicy policy = new WebAuthnPolicy();
    policy.setRpId("auth.staging.invalid");
    policy.setUserVerificationRequirement(Constants.WEBAUTHN_POLICY_OPTION_REQUIRED);
    when(realm.getWebAuthnPolicy()).thenReturn(policy);
  }

  private void wireSession() {
    factories.put(
        WebAuthnSessionNotesAuthenticatorFactory.PROVIDER_ID,
        new WebAuthnSessionNotesAuthenticatorFactory());
    factories.put(OTP_FORM, new OTPFormAuthenticatorFactory());
    factories.put(PASSWORD_FORM, new UsernamePasswordFormFactory());
    factories.put(COOKIE, new CookieAuthenticatorFactory());
    when(session.getKeycloakSessionFactory()).thenReturn(sessionFactory);
    when(sessionFactory.getProviderFactory(any(), anyString()))
        .thenAnswer(
            i -> {
              Class<?> spi = i.getArgument(0);
              String id = i.getArgument(1);
              if (spi == Authenticator.class) {
                authenticatorsAsked.add(id);
                return factories.get(id);
              }
              if (spi == RequiredActionProvider.class && WEBAUTHN_REGISTER.equals(id)) {
                return new WebAuthnRegisterFactory();
              }
              return null;
            });
    Function<String, Authenticator> provider =
        id -> {
          authenticatorsAsked.add(id);
          if (WebAuthnSessionNotesAuthenticatorFactory.PROVIDER_ID.equals(id)) {
            return new WebAuthnSessionNotesAuthenticator(session);
          }
          return OTP_FORM.equals(id) ? new OTPFormAuthenticator() : null;
        };
    when(session.getProvider(Authenticator.class, WebAuthnSessionNotesAuthenticatorFactory.PROVIDER_ID))
        .thenAnswer(i -> provider.apply(WebAuthnSessionNotesAuthenticatorFactory.PROVIDER_ID));
    when(session.getProvider(Authenticator.class, OTP_FORM))
        .thenAnswer(i -> provider.apply(OTP_FORM));
    WebAuthnCredentialProvider webAuthnCredentials = mock(WebAuthnCredentialProvider.class);
    when(webAuthnCredentials.getType()).thenReturn(WebAuthnCredentialModel.TYPE_TWOFACTOR);
    when(webAuthnCredentials.getMetadataService()).thenReturn(mock(WebAuthnMetadataService.class));
    when(session.getProvider(CredentialProvider.class, WebAuthnCredentialProviderFactory.PROVIDER_ID))
        .thenReturn(webAuthnCredentials);
    OTPCredentialProvider otpCredentials = mock(OTPCredentialProvider.class);
    when(otpCredentials.getType()).thenReturn(OTPCredentialModel.TYPE);
    when(session.getProvider(CredentialProvider.class, OTPCredentialProviderFactory.PROVIDER_ID))
        .thenReturn(otpCredentials);
    KeycloakContext keycloakContext = mock(KeycloakContext.class);
    when(session.getContext()).thenReturn(keycloakContext);
    when(keycloakContext.getAuthenticationSession()).thenReturn(authSession);
    when(keycloakContext.resolveLocale(user)).thenReturn(Locale.ENGLISH);
    when(processor.getSession()).thenReturn(session);
    when(processor.getRealm()).thenReturn(realm);
    when(processor.getAuthenticationSession()).thenReturn(authSession);
    // AuthenticationProcessor's own two answers, as 26.7.4 gives them
    when(processor.isSuccessful(any()))
        .thenAnswer(
            i ->
                statuses.get(i.<AuthenticationExecutionModel>getArgument(0).getId())
                    == ExecutionStatus.SUCCESS);
    when(processor.createFlowExecution(anyString(), any()))
        .thenAnswer(
            i -> {
              String flowId = i.getArgument(0);
              AuthenticationFlow subflow =
                  new DefaultAuthenticationFlow(processor, flows.get(flowId));
              created.put(flowId, subflow);
              return subflow;
            });
    when(processor.getRequest()).thenReturn(request);
    when(request.getHttpMethod()).thenReturn(HttpMethod.POST);
    when(request.getDecodedFormParameters()).thenReturn(formParameters);
  }

  private void wireAuthenticationSession() {
    when(authSession.getExecutionStatus()).thenReturn(statuses);
    doAnswer(i -> statuses.put(i.getArgument(0), i.getArgument(1)))
        .when(authSession)
        .setExecutionStatus(anyString(), any());
    when(authSession.getAuthenticatedUser()).thenReturn(user);
    when(authSession.getRequiredActions()).thenAnswer(i -> Set.copyOf(requiredActions));
    doAnswer(i -> requiredActions.add(i.getArgument(0)))
        .when(authSession)
        .addRequiredAction(anyString());
  }

  private void wireUser() {
    when(user.getId()).thenReturn(Fixtures.USER_ID);
    when(user.credentialManager()).thenReturn(credentials);
    when(credentials.isConfiguredFor(anyString()))
        .thenAnswer(i -> stored.stream().anyMatch(c -> c.getType().equals(i.getArgument(0))));
    when(credentials.getStoredCredentialsStream()).thenAnswer(i -> stored.stream());
    when(credentials.getStoredCredentialsByTypeStream(anyString()))
        .thenAnswer(
            i -> stored.stream().filter(c -> c.getType().equals(i.<String>getArgument(0))));
    // getConfiguredUserStorageCredentialTypesStream (deprecated) stays Mockito's empty stream:
    // no user federation is configured
  }

  /** The authenticator context, behaving as AuthenticationProcessor.Result does for a challenge. */
  private void wireContext() {
    when(processor.createAuthenticatorContext(any(), any(), any()))
        .thenAnswer(
            i -> {
              contextExecution = i.getArgument(0);
              contextStatus = null;
              contextChallenge = null;
              return context;
            });
    when(context.getExecution()).thenAnswer(i -> contextExecution);
    when(context.getStatus()).thenAnswer(i -> contextStatus);
    when(context.getChallenge()).thenAnswer(i -> contextChallenge);
    doAnswer(
            i -> {
              contextStatus = FlowStatus.CHALLENGE;
              contextChallenge = i.getArgument(0);
              return null;
            })
        .when(context)
        .challenge(any());
    when(context.getSession()).thenReturn(session);
    when(context.getRealm()).thenReturn(realm);
    when(context.getUser()).thenReturn(user);
    when(context.getAuthenticationSession()).thenReturn(authSession);
    when(context.form()).thenReturn(form);
    when(form.createLoginWebAuthn()).thenReturn(webAuthnPage);
    when(form.createWebAuthnErrorPage()).thenReturn(webAuthnErrorPage);
    // what the stock action reads and calls
    when(context.getHttpRequest()).thenReturn(request);
    when(context.getEvent()).thenReturn(mock(EventBuilder.class, RETURNS_SELF));
    KeycloakUriInfo uriInfo = mock(KeycloakUriInfo.class);
    when(uriInfo.getBaseUri()).thenReturn(URI.create("https://auth.staging.invalid/"));
    when(context.getUriInfo()).thenReturn(uriInfo);
    UserProvider users = mock(UserProvider.class);
    when(session.users()).thenReturn(users);
    when(users.getUserById(realm, Fixtures.USER_ID)).thenReturn(user);
    doAnswer(
            i -> {
              contextStatus = FlowStatus.SUCCESS;
              return null;
            })
        .when(context)
        .success(anyString());
    doAnswer(
            i -> {
              contextStatus = FlowStatus.FAILED;
              contextChallenge = i.getArgument(1);
              return null;
            })
        .when(context)
        .failure(any(AuthenticationFlowError.class), any(Response.class));
  }
}
