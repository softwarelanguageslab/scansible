package matcher.matching
import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.semanticcpg.language.*
import matcher.DependencyTag
import matcher.traversals.*
import overflowdb.*

/** Mark methods that use the `community.general` `CmdRunner` class. */
object CommunityGeneralCmdRunnerMatcher extends DependencyMatcher {

  extension (call: Call) {
    private def isValidCmdRunner: Boolean =
      call.receiver.isIdentifier.exists(_.typeFullName.contains("community/general/plugins/module_utils/cmd_runner.py"))
  }

  override def mark(cpg: Cpg)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    val cmdRunnerCalls = cpg.call("CmdRunner").filter(_.isValidCmdRunner)

    cmdRunnerCalls
      .flatMap(c =>
        c.literalArgument(call => call.argument.find(_.argumentName.contains("command")).orElse(call.arguments(2).headOption))
          .map(c.method -> _))
      .foreach((m, lib) =>
        // println(s"Marking CommunityGeneralCmdRunner on ${m.fullName} of $lib")
        m.markDependency(DependencyTag.CommunityGeneralCmdRunner, lib)
      )
}
