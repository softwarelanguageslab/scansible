package matcher.postprocessing

import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.passes.CpgPass
import io.shiftleft.semanticcpg.language.*
import overflowdb.*

import matcher.traversals.*

/**
 * Joern does not add a DDG edge between a module variable initialised with a non-literal
 * and usages of this variable in methods defined in the module. We need such DDG edges.
 */
class LinkNonLiteralModuleVariablesPass(cpg: Cpg) extends CpgPass(cpg) {

  extension (id: Identifier) {
    private def closureBindings: Iterator[ClosureBinding] =
      id._refOut._refIn.collectAll[ClosureBinding]
  }

  extension (bindings: Traversal[ClosureBinding]) {
    private def usedInMethods: Iterator[Method] =
      bindings._captureIn._refOut.collectAll[Method]
  }

  override def run(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    // Filter out invalid identifier names, like "*", which get inserted by Joern for "from ... import *" statements.
    val moduleVariables = cpg.method.fullName(".*:<module>").assignment.assignedIdentifier.filterNot(_.name == "*")

    moduleVariables.foreach(modVar =>
      val usingMethods = modVar.closureBindings.usedInMethods
      val usingIdentifiers = usingMethods.ast.isIdentifier.name(modVar.name)
      usingIdentifiers.foreach(id =>
        builder.addEdge(modVar, id, EdgeTypes.REACHING_DEF, PropertyNames.VARIABLE, id.name)
      )
    )
}
