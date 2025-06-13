package matcher.postprocessing

import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.passes.CpgPass
import io.shiftleft.semanticcpg.language.*
import overflowdb.*

import matcher.traversals.*

class LinkSelfCallsPass(cpg: Cpg) extends CpgPass(cpg) {
  extension (cpg: Cpg) {
    private def selfCalls: Iterator[nodes.Call] =
      cpg.call.filter(_.arguments(0).exists(_.code == "self"))
  }

  extension (c: nodes.Call) {
    private def possibleMethodsFromTypeHierarchy: Iterator[nodes.Method] =
      c.method.typeDecl.iterator.flatMap(typeDecl =>
        val ownMethod = typeDecl.definedMethods.filter(_.name == c.name).headOption
        // If method not defined in class, it'll be the first method in a superclass
        val ownOrSuper = ownMethod.orElse(typeDecl.superMethod(c.name).headOption)

        // In any case, due to late binding of `self`, it could be any method of a subclass too
        val subMethods = typeDecl.subDefinedMethodsTransitive.filter(_.name == c.name)

        ownMethod.iterator ++ subMethods
      )
  }

  override def run(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    cpg.selfCalls.foreach(c =>
      val methods = c.possibleMethodsFromTypeHierarchy.map(_.fullName).toSeq
      builder.setNodeProperty(c, PropertyNames.DYNAMIC_TYPE_HINT_FULL_NAME, methods)
    )
}
