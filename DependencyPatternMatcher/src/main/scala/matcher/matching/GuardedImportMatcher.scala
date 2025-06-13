package matcher.matching
import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.semanticcpg.language.*
import matcher.DependencyTag
import matcher.traversals.*
import overflowdb.*

/** Mark methods that implement a guarded import check. */
object GuardedImportMatcher extends DependencyMatcher {
  override def mark(cpg: Cpg)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    val tryBlocksWithImports = cpg.tryBlock.where(_.ast.isImportCall)
    val failureVariablesToLibs = tryBlocksWithImports.flatMap(tryBlock =>
      val importedLibraries = tryBlock.ast.isImportCall.importedLibrary.toSet
      // Extract all identifiers that are assigned in the try-except block (both try and except). However, don't use
      // identifiers that are assigned with the result of an import (since imports get rewritten to `lib = import(, lib)`
      val assignedLibraryVariables = tryBlock.ast.isImportCall.inAssignment.assignedIdentifier.toSet
      val assignedVariables = tryBlock.ast.assignment.assignedIdentifier.dedup.toSet -- assignedLibraryVariables
      assignedVariables.flatMap(av => importedLibraries.map(av -> _))
    ).groupMap(_._1)(_._2)

    // Checks of a failure variable
    val failureCheckingMethods = failureVariablesToLibs.iterator.flatMap((v, libs) =>
      v.ddgOut.inCondition.map(_.method -> libs)
    ).dedup

    failureCheckingMethods.foreach((method, libs) =>
      // println(s"Marking GuardedImport on ${method.fullName} of $libs")
      method.markDependency(DependencyTag.GuardedImport, libs)
    )
}
