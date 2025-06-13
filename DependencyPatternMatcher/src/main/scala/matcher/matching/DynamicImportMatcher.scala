package matcher.matching
import io.joern.dataflowengineoss.language.*
import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.semanticcpg.language.*
import matcher.DependencyTag
import matcher.traversals.*
import overflowdb.*

  /** Mark methods that implement a dynamic import check, i.e., call importlib.import_module */
object DynamicImportMatcher extends DependencyMatcher {
  override def mark(cpg: Cpg)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    val importModuleCalls = cpg.call("import_module")
    // Need additional filtering to make sure we're only considering calls to import_module from importlib.
    // We handle 2 cases:
    //  - `from importlib import import_module … import_module(…)`
    //  - `import importlib … importlib.import_module(…)`
    val validCalls = importModuleCalls.filter(c =>
      c.argument.headOption.isIdentifier.headOption match {
        case Some(ident) => ident.typeFullName == "importlib.py:<module>"
        case None => c.receiver.isIdentifier.typeFullName("importlib.py:<module>.import_module").nonEmpty
      }
    )

    validCalls
      .flatMap(c => c.literalArgument(1).map(c.method -> _))
      .foreach((m, lib) =>
        // println(s"Marking DynamicImport on ${m.fullName} of $lib")
        m.markDependency(DependencyTag.DynamicImport, lib)
      )
}
