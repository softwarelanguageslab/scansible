package matcher.postprocessing

import io.joern.pysrc2cpg.Constants
import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.passes.CpgPass
import io.shiftleft.semanticcpg.language.*
import overflowdb.*

import matcher.traversals.*

/** Add call graph edges for explicit super calls. Ignores multiple inheritance. */
class LinkExplicitSuperCallsPass(cpg: Cpg) extends CpgPass(cpg) {

  extension (cpg: Cpg) {
    private def explicitSuperCalls: Iterator[Call] =
      // Calls to super()
      cpg.call.methodFullName("__builtin.super")
        // Only those in classes
        .where(_.method.typeDecl)
        // Find the `super()._()` calls
        .flatMap(c =>
          // tmp identifier for the result of the super() call
          val resultIdentifier = c.inAssignment.assignedIdentifier
          // Follow references to the tmp variable, then find usages in calls
          resultIdentifier.flatMap(
            _.ddgOut.inAst.isCall.methodFullName("__builtin.super.<returnValue>.*"))
        )
  }

  override def run(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    cpg.explicitSuperCalls.foreach(c =>
      val superMethod = c.method.typeDecl.head.superMethod(c.name).l
      superMethod.foreach(sm => builder.addEdge(c, sm, EdgeTypes.CALL))
    )
}
