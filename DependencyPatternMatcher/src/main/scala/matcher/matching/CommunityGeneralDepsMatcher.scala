package matcher.matching
import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.semanticcpg.language.*
import matcher.DependencyTag
import matcher.traversals.*
import overflowdb.*

/** Mark methods that use the `community.general` `deps` pattern. */
object CommunityGeneralDepsMatcher extends DependencyMatcher {

  extension (call: Call) {
    private def isCallToDeps: Boolean =
      val receiverOpt = call.argument.headOption.isIdentifier.headOption
      receiverOpt match {
        case Some(receiver) => receiver.name == "deps" && receiver.typeFullName.contains("community/general/plugins/module_utils")
        case _ => false
      }
  }

  override def mark(cpg: Cpg)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    val depsDeclareCalls = cpg.call("declare").filter(_.isCallToDeps).l
    val fileToDeclares = depsDeclareCalls.map(decl => decl -> decl.file.head).groupMap(_._2)(_._1).view.mapValues(_.toSet)
    val fileToImports = fileToDeclares.mapValues(_.flatMap(declareCall => {
      // To get the imports, navigate up the AST to the Block that represents the context manager,
      // then descend to import calls.
      declareCall.start.repeat(_.astParent)(_.until(_.isBlock)).ast.isImportCall.importedLibrary.toSet
    }))

    // Mark each method that calls `deps.validate`.
    fileToImports.foreach((file, imports) =>
      val validateCalls = file.ast.isCallTo("validate").filter(_.isCallToDeps).method.dedup.l
      /*validateCalls.foreach(m =>
        println(s"Marking CommunityGeneralDeps on ${m.fullName} of $imports")
      )*/
      validateCalls.iterator.markDependency(DependencyTag.CommunityGeneralDeps, imports)
    )
}
