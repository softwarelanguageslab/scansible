package matcher.postprocessing

import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.passes.CpgPass
import io.shiftleft.semanticcpg.language.*
import overflowdb.*

class LinkInheritanceAfterTypeRecoveryPass(cpg: Cpg) extends CpgPass(cpg) {
  override def run(builder: BatchedUpdate.DiffGraphBuilder): Unit =
    cpg.typeDecl.filter(needsAdditionalResolution).foreach(td =>
      val leftoverNames = getLeftoverNames(td)
      cpg.typ.fullNameExact(leftoverNames: _*)
        .foreach(tgt => builder.addEdge(td, tgt, EdgeTypes.INHERITS_FROM))
    )
    
  extension (td: TypeDecl) {
    private def nonTrivialInheritedNames: IndexedSeq[String] =
      td.inheritsFromTypeFullName.filterNot(parent => parent == "ANY" || parent == "object")
  }

  private def getLeftoverNames(td: TypeDecl): Seq[String] =
    val inheritedNames = td.nonTrivialInheritedNames.toSet
    val inheritedTypeNames = td.baseTypeDecl.fullName.toSet
    (inheritedNames -- inheritedTypeNames).toSeq

  private def needsAdditionalResolution(td: TypeDecl): Boolean =
    getLeftoverNames(td).nonEmpty
}
