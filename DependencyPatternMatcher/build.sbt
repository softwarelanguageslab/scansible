ThisBuild / version := "0.1.0-SNAPSHOT"

ThisBuild / scalaVersion := "3.3.1"

lazy val root = (project in file("."))
  .settings(
    name := "matcher.DependencyPatternMatcher",
    libraryDependencies += "io.joern" %% "pysrc2cpg" % "2.0.250",
    libraryDependencies += "org.scalatest" %% "scalatest" % "3.2.18" % "test"
  )
