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

  /** How a check ended: an answer, which is yes, no or neither, or why there is none. */
  private enum Outcome:
    case Answered(answer: Option[Boolean], message: Option[String] = None)
    case Failed(message: String)
    case TimedOut

    /** The reply, with the time for all but a timeout, where the check did not end. */
    def reply(seconds: Double): Json = this match
      case Answered(answer, message) =>
        Json.fromFields(
          List("answer" -> answer.fold(Json.Null)(Json.fromBoolean), "seconds" -> Json.fromDoubleOrNull(seconds))
            ++ message.map(text => "message" -> Json.fromString(text))
        )
      case Failed(message) =>
        Json.obj(
          "failure" -> Json.fromString("error"),
          "message" -> Json.fromString(message),
          "seconds" -> Json.fromDoubleOrNull(seconds)
        )
      case TimedOut => Json.obj("failure" -> Json.fromString("timeout"))

  import Outcome.*

  private def check(fused: String): Outcome =
    val schema = parse(fused).fold(throw _, identity)
    val env = Environment(mutable.Map[VarName, SchemaExpr]())
    val (root, translated) = translateAsRef(schema, schema, env)
    val (stratifiedRoot, stratified) = stratify(root, translated)
    val extended = newExtendedEnv(notComplete(stratified))
    val result = varAllOf(stratifiedRoot.asInstanceOf[CVar], varTrue, extended)
    if result == varFalse then Answered(Some(true))
    else
      generate.Generate.generateFromCVarEEFile(result, extended, schema) match
        case UnSat    => Answered(Some(true))
        case WhoKnows => Answered(None)
        case Witness(value) =>
          // As the artifact does: a witness counts unless the validator rejects it, and a
          // validator that fails says nothing.
          val rejected =
            try !validateStringWitness(schema.toString, value.toString).isEmpty
            catch case NonFatal(_) => false
          if rejected then Failed("the witness is not an instance")
          else Answered(Some(false), Some(value.noSpaces.take(300)))

  private def guarded(fused: String): Outcome =
    try check(fused)
    catch
      case _: InterruptedException => TimedOut
      // Also a StackOverflowError: the next request can still be answered.
      case e: Throwable => Failed(s"${e.getClass.getSimpleName}: ${e.getMessage}".take(300))

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
          case Left(e) => outcome = Failed(s"combineSchemas: ${e.getClass.getSimpleName}: ${e.getMessage}".take(300))
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
              outcome = TimedOut
            else outcome = finished
        protocol.println(outcome.reply(seconds).noSpaces)
      }
    }
