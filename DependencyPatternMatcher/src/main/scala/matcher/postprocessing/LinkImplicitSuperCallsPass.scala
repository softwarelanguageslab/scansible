package matcher.postprocessing

import io.joern.pysrc2cpg.Constants
import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.passes.CpgPass
import io.shiftleft.semanticcpg.language.*
import matcher.traversals.*
import overflowdb.*

/** Add call graph edges for implicit super calls, i.e., subclasses that do not override a superclass method. */
class LinkImplicitSuperCallsPass(cpg: Cpg) extends CpgPass(cpg) {

  extension (cpg: Cpg) {
    private def inheritedMethods: Iterator[Method] =
      cpg.method.isExternal(true).filter(_.astParent.isTypeDecl)
  }

  override def run(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    cpg.inheritedMethods.foreach(m =>
      val superMethods = m.typeDecl.get.superMethod(m.name).l
      superMethods.foreach(sm =>
        // Need to create a fake call node in the body of the fake method to simulate the call: CALL edges cannot go from
        // method to method
        val callNode = createFakeCallNode(m, sm, builder)
        builder.addEdge(callNode, sm, EdgeTypes.CALL)
      )
    )

  private def createFakeCallNode(caller: Method, callee: Method, builder: BatchedUpdate.DiffGraphBuilder): NewCall =
    val callNode = NewCall()
      .code("<fake>")
      .name(callee.name)
      .methodFullName(callee.fullName)
      .dispatchType(DispatchTypes.DYNAMIC_DISPATCH)
      .typeFullName(Constants.ANY)
    builder.addNode(callNode)
    builder.addEdge(caller, callNode, EdgeTypes.CONTAINS)

    callNode
}
