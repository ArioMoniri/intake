package intake.keycloak.webauthn;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.ServiceLoader;
import org.junit.jupiter.api.Test;
import org.keycloak.authentication.AuthenticatorFactory;
import org.keycloak.authentication.authenticators.browser.WebAuthnAuthenticatorFactory;
import org.keycloak.models.KeycloakSession;

class WebAuthnSessionNotesAuthenticatorFactoryTest {

  private final WebAuthnSessionNotesAuthenticatorFactory factory =
      new WebAuthnSessionNotesAuthenticatorFactory();
  private final WebAuthnAuthenticatorFactory stock = new WebAuthnAuthenticatorFactory();

  @Test
  void theProviderIdIsTheOneTheRealmFlowNames() {
    // infra/keycloak/dev-realm.json, flow "staff second factor"; held there by
    // tests/admin/test_webauthn_session_notes_provider.py
    assertEquals("intake-webauthn-session-notes", factory.getId());
    assertEquals(WebAuthnSessionNotesAuthenticatorFactory.PROVIDER_ID, factory.getId());
    assertNotEquals(stock.getId(), factory.getId());
  }

  @Test
  void itCreatesTheNoteWritingAuthenticator() {
    assertInstanceOf(
        WebAuthnSessionNotesAuthenticator.class, factory.create(mock(KeycloakSession.class)));
  }

  @Test
  void everythingButTheIdAndTheLabelsIsTheStockFactorys() {
    assertEquals(stock.getReferenceCategory(), factory.getReferenceCategory());
    assertArrayEquals(stock.getRequirementChoices(), factory.getRequirementChoices());
    assertEquals(stock.isUserSetupAllowed(), factory.isUserSetupAllowed());
    assertEquals(stock.isConfigurable(), factory.isConfigurable());
    assertEquals(stock.getConfigProperties(), factory.getConfigProperties());
    assertInstanceOf(WebAuthnAuthenticatorFactory.class, factory);
  }

  @Test
  void userSetupIsAllowedSoARequiredStepCanSendANewUserToRegistration() {
    // INT-550: Keycloak marks a REQUIRED execution SETUP_REQUIRED for a user without the
    // credential only if its factory allows user setup; held here outright, not only as the
    // stock factory's value, so a refactor away from the stock factory cannot drop it
    assertTrue(factory.isUserSetupAllowed());
  }

  @Test
  void theServiceFileRegistersTheFactory() throws IOException {
    String path = "META-INF/services/" + AuthenticatorFactory.class.getName();
    try (InputStream in = getClass().getClassLoader().getResourceAsStream(path)) {
      assertNotNull(in, path);
      List<String> lines =
          new String(in.readAllBytes(), StandardCharsets.UTF_8)
              .lines()
              .map(String::strip)
              .filter(line -> !line.isEmpty() && !line.startsWith("#"))
              .toList();
      assertEquals(List.of(WebAuthnSessionNotesAuthenticatorFactory.class.getName()), lines);
    }
    boolean loaded =
        ServiceLoader.load(AuthenticatorFactory.class).stream()
            .anyMatch(p -> p.type() == WebAuthnSessionNotesAuthenticatorFactory.class);
    assertTrue(loaded);
  }
}
