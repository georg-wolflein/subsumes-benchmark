import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.confluent.kafka.schemaregistry.json.JsonSchema;
import java.io.BufferedReader;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * The adapter for the JSON Schema compatibility check of Confluent Schema Registry: answers the
 * runner's requests, one JSON line each.
 *
 * <p>"A accepts every instance of B" is the registry's backward compatibility with A as the new
 * schema and B as the previous one: a consumer on the new schema can read what was written with
 * the previous one. The registry answers compatible or not, so it never declines.
 */
public final class Adapter {
  private static final String DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";
  private static final long STACK_BYTES = 512L * 1024 * 1024;
  private static final ObjectMapper MAPPER = new ObjectMapper();

  private record Outcome(String answer, String detail) {}

  private static Outcome check(String a, String b) {
    try {
      List<String> problems = new JsonSchema(a).isBackwardCompatible(new JsonSchema(b));
      return problems.isEmpty() ? new Outcome("yes", null) : new Outcome("no", problems.get(0));
    } catch (Throwable e) { // also a StackOverflowError: the next request can still be answered
      String detail = e.getClass().getSimpleName() + ": " + e.getMessage();
      if (e.getCause() != null) {
        detail += " (" + e.getCause().getMessage() + ")";
      }
      return new Outcome("error", detail);
    }
  }

  /**
   * A schema of a request as the text that the registry takes. The registry reads a schema
   * without {@code $schema} as draft-07; the corpus is 2020-12.
   */
  private static String text(JsonNode schema) throws Exception {
    if (schema instanceof ObjectNode object && !object.has("$schema")) {
      object.put("$schema", DRAFT_2020_12);
    }
    return MAPPER.writeValueAsString(schema);
  }

  public static void main(String[] args) throws Exception {
    // The library logs while it works; the runner owns the standard output.
    PrintStream protocol =
        new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8);
    System.setOut(System.err);
    BufferedReader requests =
        new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    protocol.println("{\"ready\":true}");
    for (String line = requests.readLine(); line != null; line = requests.readLine()) {
      JsonNode request = MAPPER.readTree(line);
      String a = text(request.get("a"));
      String b = text(request.get("b"));
      long timeoutMillis = (long) (request.get("timeout").asDouble() * 1000);

      Outcome[] outcome = new Outcome[1];
      Thread thread = new Thread(null, () -> outcome[0] = check(a, b), "check", STACK_BYTES);
      thread.setDaemon(true);
      // The clock runs from the schemas as text to the answer, so that each is parsed once
      // in that time.
      long start = System.nanoTime();
      thread.start();
      thread.join(timeoutMillis);
      double seconds = (System.nanoTime() - start) / 1e9;
      if (thread.isAlive()) {
        thread.interrupt();
        thread.join(1000);
        if (thread.isAlive()) {
          // The check cannot be stopped and would slow down what follows. Saying nothing makes
          // the runner record the timeout and start a new process.
          Thread.sleep(Long.MAX_VALUE);
        }
        outcome[0] = new Outcome("timeout", null);
      }
      ObjectNode reply = MAPPER.createObjectNode();
      reply.put("answer", outcome[0].answer());
      reply.put("seconds", seconds);
      reply.put("detail", outcome[0].detail());
      protocol.println(MAPPER.writeValueAsString(reply));
    }
  }
}
