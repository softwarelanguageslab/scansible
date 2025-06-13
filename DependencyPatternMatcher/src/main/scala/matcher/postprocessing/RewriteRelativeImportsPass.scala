package matcher.postprocessing

import io.joern.pysrc2cpg.ImportsPass
import io.shiftleft.codepropertygraph.Cpg
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.semanticcpg.language.*

class RewriteRelativeImportsPass(cpg: Cpg) extends ImportsPass(cpg) {
  override def importedEntityFromCall(call: Call): String = {
    call.argument.code.l match {
      case List(where, what) if where.startsWith(".") =>
        val whereAbsolute = convertWhereToAbsolute(where, call)
        s"$whereAbsolute.$what"
      case List(where, what, _) if where.startsWith(".") =>
        val whereAbsolute = convertWhereToAbsolute(where, call)
        s"$whereAbsolute.$what"
      case _ => super.importedEntityFromCall(call)
    }
  }

  private def convertWhereToAbsolute(where: String, call: Call): String =
    val modulePath = call.file.head.name
    val moduleFqnParts = modulePath.replace("/", ".").replaceFirst("\\.py$", "").split("\\.")
    val relativeDepth = where.takeWhile(_ == '.').length
    val whereName = where.drop(relativeDepth)

    val whereAbsolutePrefix = moduleFqnParts.slice(0, moduleFqnParts.length - relativeDepth)
    if whereName.isEmpty then whereAbsolutePrefix.mkString(".") else s"${whereAbsolutePrefix.mkString(".")}.$whereName"
}
