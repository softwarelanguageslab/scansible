package matcher.postprocessing

import io.joern.pysrc2cpg.PythonInheritanceNamePass
import io.shiftleft.codepropertygraph.Cpg
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.semanticcpg.language.*

class PythonInheritanceNamePassFixed(cpg: Cpg) extends PythonInheritanceNamePass(cpg) {
  override protected def resolveInheritedTypeFullName(td: TypeDecl, builder: DiffGraphBuilder): Seq[TypeDeclBase] = {
    // Joern is inaccurate in its resolution of base classes. We'll use the resolved imports where possible.
    td.inheritsFromTypeFullName.flatMap(resolveType(td, _))
    // If we couldn't find the import, we'll let the type resolution do its thing. It'll qualify the parent class
    // name, and in a subsequent pass, we'll link it properly.
  }

  private def resolveType(decl: TypeDecl, inheritedName: String): Option[TypeDeclBase] =
    var parent = decl.astParent
    var found: Option[TypeDeclBase] = None

    // Walk the AST parents upward to find a match for the declared parent, either adjacent to the declaration, or
    // in an outer scope.
    while parent._astIn.nonEmpty && found.isEmpty do
      val curr = parent
      parent = curr.astParent

      found = curr.astChildren.collectFirst {
        // Type declarations local to the file
        case n: TypeDecl if n.name == inheritedName => n
      }.headOption
      
    found

}
