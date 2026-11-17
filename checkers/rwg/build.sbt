// The adapter is compiled together with the sources of RWG, which is not published as a
// library. They are the submodule sources/inclusion-artifact, at the commit the corpus is
// built from; `make sources` fetches it.
val artifact = file("../../sources/inclusion-artifact")

ThisBuild / scalaVersion := "3.3.5"

lazy val javaArguments =
  taskKey[File]("Writes the options that put the adapter on the class path to a file for java")

lazy val root = (project in file("."))
  .settings(
    name := "rwg-adapter",
    Compile / unmanagedSourceDirectories += artifact / "src" / "main" / "scala",
    Compile / unmanagedJars += artifact / "lib" / "JsonSchema_to_Algebra-0.0.1-SNAPSHOT.jar",
    // What the artifact's own build.sbt lists for its main sources, without logback: the
    // jar above brings slf4j-simple, which is the binding the artifact ends up with too.
    libraryDependencies ++= Seq(
      "io.circe" %% "circe-core" % "0.14.1",
      "io.circe" %% "circe-generic" % "0.14.1",
      "io.circe" %% "circe-parser" % "0.14.1",
      "dk.brics" % "automaton" % "1.12-4",
      "au.com.bytecode" % "opencsv" % "2.4",
      "org.apache.commons" % "commons-text" % "1.10.0",
      "org.antlr" % "antlr4-runtime" % "4.9.3",
      "com.networknt" % "json-schema-validator" % "1.5.9",
      "com.typesafe.scala-logging" %% "scala-logging" % "3.9.5",
      "junit" % "junit" % "4.13.2"
    ),
    javaArguments := {
      val classPath = (Runtime / fullClasspath).value.files.mkString(java.io.File.pathSeparator)
      val file = target.value / "java.args"
      IO.write(file, s"""-cp "${classPath.replace("\\", "\\\\")}"\n""")
      file
    }
  )
