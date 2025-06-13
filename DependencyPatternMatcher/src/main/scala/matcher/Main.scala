package matcher

import scala.util.{Try, Success, Failure}
import better.files.File

case class InputProject(projectId: String, projectPath: String, basePath: String)
case class OutputRow(projectId: String, plugin: String, dependency: String, pattern: String)


object Main:
  private var failedProjects: List[(String, String)] = Nil

  def main(args: Array[String]): Unit =

    /*val coll = "paloaltonetworks/panos"
    val plugin = "modules/panos_ipv6_address"
    val results = new DependencyPatternMatcher().run(s"/var/folders/d6/pq_t2ms55szdq598jctyf1nw0000gn/T/tmpf7mrcrzm/ansible_collections/$coll/plugins", s"ansible_collections/$coll/plugins")
    val x = results.toList.map((plugin, dependencySet) =>
      val pluginName = plugin.split(":").head.replaceAll("\\.py$", "").replace(s"ansible_collections/$coll/plugins/", "")
      pluginName -> dependencySet
    ).groupMapReduce(_._1)(_._2)((s1, s2) => s1 ++ s2)
    x.getOrElse(plugin, Set()).foreach(println)
    return*/

    if (args.length != 2) {
      println("Need input JSON and output CSV")
    } else {
      val input = parseInput(File(args(0)))
      val outFile = File(args(1))
      if outFile.notExists then {
        writeOutputHeader(outFile)
        input.foreach(processProject(_, outFile))
      }

      /*failedProjects.foreach((p, err) =>
        Console.err.println(s"$p failed: $err")
      )
      if failedProjects.nonEmpty then sys.exit(1)*/
    }

  private def parseInput(inputFile: File): Seq[InputProject] =
    val inputJson = ujson.read(inputFile.contentAsString)

    inputJson.arr.map(projectJson =>
      val projectDict = projectJson.obj
      InputProject(projectDict("projectId").str, projectDict("projectPath").str, projectDict("basePath").str)
    ).toSeq

  private def processProject(project: InputProject, outFile: File): Unit =
    if File(project.projectPath).notExists then
      println(s"Ignoring ${project.projectId}: ${project.projectPath} does not exist")
      return

    println(s"Processing project ${project.projectId}")
    val dependencyMap = new DependencyPatternMatcher().run(project.projectPath, project.basePath)
    val dependencyPattern = "(\\w+):(.+)".r
    // Convert the map to a list first, otherwise we might lose results
    val outputRows = dependencyMap.toList.map((plugin, dependencySet) =>
      val pluginName = plugin.split(":").head.replaceAll("\\.py$", "").replace(s"${project.basePath}/", "")
      pluginName -> dependencySet
    ).groupMapReduce(_._1)(_._2)((s1, s2) => s1 ++ s2)
      .view.filterKeys(pluginName => !pluginName.startsWith("module_utils") && !pluginName.startsWith("plugin_utils"))
      .flatMap((pluginName, dependencySet) =>
        dependencySet.map { case dependencyPattern(pattern, dependency) =>
          OutputRow(project.projectId, pluginName, dependency, pattern)
        }
      ).toList

    appendOutput(outFile, outputRows)
    
    /*Try {
      new DependencyPatternMatcher().run(project.projectPath, project.basePath)
    } match {
      case Success(dependencyMap) =>
        val dependencyPattern = "(\\w+):(.+)".r
        // Convert the map to a list first, otherwise we might lose results
        val outputRows = dependencyMap.toList.map((plugin, dependencySet) =>
          val pluginName = plugin.split(":").head.replaceAll("\\.py$", "").replace(s"${project.basePath}/", "")
          pluginName -> dependencySet
        ).groupMapReduce(_._1)(_._2)((s1, s2) => s1 ++ s2)
          .view.filterKeys(pluginName => !pluginName.startsWith("module_utils") && !pluginName.startsWith("plugin_utils"))
          .flatMap((pluginName, dependencySet) =>
            dependencySet.map { case dependencyPattern(pattern, dependency) =>
              OutputRow(project.projectId, pluginName, dependency, pattern)
            }
          ).toList

        appendOutput(outFile, outputRows)
      case Failure(e) =>
        Console.err.println(s"${Console.RED_B}${project.projectId} FAILED! ${e.toString}${Console.RESET}")
        failedProjects ::= (project.projectId -> e.toString)
    }*/

  private def writeOutputHeader(outputFile: File): Unit =
    val header = List("projectId", "plugin", "dependency", "pattern").mkString(",")
    outputFile.writeText(header)

  private def appendOutput(outputFile: File, outputRows: List[OutputRow]): Unit =
    val content = outputRows.map(row => row.productIterator.mkString(","))
    outputFile.appendLines(content : _*)
