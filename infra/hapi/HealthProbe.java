// Healthcheck for the distroless HAPI image: GET /fhir/metadata must answer 200.
// Run as a single-file source program (JEP 330): `java /probe/HealthProbe.java`.
import java.net.HttpURLConnection;
import java.net.URL;

public class HealthProbe {
    public static void main(String[] args) throws Exception {
        URL url = new URL("http://localhost:8080/fhir/metadata");
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(5000);
        conn.setRequestMethod("GET");
        int code = conn.getResponseCode();
        if (code != 200) {
            System.err.println("HAPI metadata returned " + code);
            System.exit(1);
        }
    }
}
