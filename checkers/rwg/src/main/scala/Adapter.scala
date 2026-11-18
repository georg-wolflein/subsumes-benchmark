import algebra.utils.*
import algebra.utils.InstanceValidation.validateStringWitness
import algebra.utils.VarNameModule.*
import generate.{UnSat, WhoKnows, Witness}
import io.circe.Json
import io.circe.parser.parse
import jsonschema.Included_Functions.*
import jsonschema.Translator.*
import jsonschema.varAllOf_Functions.*
import utils.SchemaProcessorLib

import java.io.{BufferedReader, FileDescriptor, FileOutputStream, InputStreamReader, OutputStream, PrintStream}
import java.nio.charset.StandardCharsets
import scala.collection.mutable
import scala.util.control.NonFatal

/** The adapter for RWG, the inclusion checker by refutational normalization: answers the
  * runner's requests, one JSON line each.
  *
  * RWG decides whether one schema is satisfiable, so "A accepts every instance of B" is asked
  * as: is `allOf: [B, not A]` unsatisfiable? RWG's own `combineSchemas` builds that document,
  * and the steps after it are those of the artifact's `RealInclusionTest`, with its Scala
  * witness generator. RWG reads the keywords of draft-07, so the runner hands it schemas
  * rewritten to that draft.
  */
object Adapter:
  private val StackBytes = 512L * 1024 * 1024

  private case class Outcome(answer: String, detail: Option[String] = None)

  private def check(fused: String): Outcome =
    val schema = parse(fused).fold(throw _, identity)
    val env = Environment(mutable.Map[VarName, SchemaExpr]())
    val (root, translated) = translateAsRef(schema, schema, env)
    val (stratifiedRoot, stratified) = stratify(root, translated)
    val extended = newExtendedEnv(notComplete(stratified))
    val result = varAllOf(stratifiedRoot.asInstanceOf[CVar], varTrue, extended)
    if result == varFalse then Outcome("yes")
    else
      generate.Generate.generateFromCVarEEFile(result, extended, schema) match
        case UnSat    => Outcome("yes")
        case WhoKnows => Outcome("unknown")
        case Witness(value) =>
          // As the artifact does: a witness counts unless the validator rejects it, and a
          // validator that fails says nothing.
          val rejected =
            try !validateStringWitness(schema.toString, value.toString).isEmpty
            catch case NonFatal(_) => false
          if rejected then Outcome("error", Some("the witness is not an instance"))
          else Outcome("no", Some(value.noSpaces.take(300)))

  private def guarded(fused: String): Outcome =
    try check(fused)
    catch
      case _: InterruptedException => Outcome("timeout")
      // Also a StackOverflowError: the next request can still be answered.
      case e: Throwable => Outcome("error", Some(s"${e.getClass.getSimpleName}: ${e.getMessage}".take(300)))

  def main(args: Array[String]): Unit =
    // RWG prints while it works; the runner owns the standard output.
    val protocol = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8)
    val silent = new PrintStream(OutputStream.nullOutputStream())
    System.setOut(silent)
    Console.withOut(silent) {
      val requests = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))
      protocol.println("""{"ready":true}""")
      Iterator.continually(requests.readLine()).takeWhile(_ != null).foreach { line =>
        val request = parse(line).fold(throw _, identity).hcursor
        // RWG takes a schema as text, so each is written back to text.
        def text(key: String) = request.get[Json](key).fold(throw _, identity).noSpaces
        val (a, b) = (text("a"), text("b"))
        val timeoutMillis = (request.get[Double]("timeout").fold(throw _, identity) * 1000).toLong

        var outcome: Outcome = null
        var seconds = 0.0
        val fused =
          try Right(SchemaProcessorLib.combineSchemas(b, a)._1)
          catch case NonFatal(e) => Left(e)
        fused match
          case Left(e) => outcome = Outcome("error", Some(s"combineSchemas: ${e.getClass.getSimpleName}: ${e.getMessage}".take(300)))
          case Right(fused) =>
            @volatile var finished: Outcome = null
            val thread = new Thread(null, () => finished = guarded(fused), "check", StackBytes)
            thread.setDaemon(true)
            // The clock runs from the fused document as text, the form RWG reads, to the answer.
            val start = System.nanoTime()
            thread.start()
            thread.join(timeoutMillis)
            seconds = (System.nanoTime() - start) / 1e9
            if thread.isAlive then
              thread.interrupt()
              thread.join(1000)
              // A check that cannot be stopped would slow down what follows. Saying nothing
              // makes the runner record the timeout and start a new process.
              if thread.isAlive then Thread.sleep(Long.MaxValue)
              outcome = Outcome("timeout")
            else outcome = finished
        val reply = Json.obj(
          "answer" -> Json.fromString(outcome.answer),
          "seconds" -> Json.fromDoubleOrNull(seconds),
          "detail" -> outcome.detail.fold(Json.Null)(Json.fromString)
        )
        protocol.println(reply.noSpaces)
      }
    }
