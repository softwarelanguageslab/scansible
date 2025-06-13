package matcher.postprocessing

import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.passes.{CpgPass, ForkJoinParallelCpgPass}
import io.shiftleft.semanticcpg.language.*
import io.shiftleft.semanticcpg.language.importresolver.EvaluatedImport
import matcher.traversals.*
import overflowdb.*

import java.nio.charset.StandardCharsets
import java.util.Base64

object LinkCrossModuleVariableUsages {
  private val SUPPORTED_TAGS: Set[String] = Set(EvaluatedImport.RESOLVED_MEMBER, EvaluatedImport.RESOLVED_TYPE_DECL)
}

/**
 * Joern does not add a data dependence between a definition of a module variable in one module
 * to a usage of that same variable in a different module. We need this information to properly
 * resolve certain types of patterns, such as Guarded Imports where the plugin imports the flag
 * from `module_utils` or `plugin_utils` and checks the flag itself.
 */
class LinkCrossModuleVariableUsages(cpg: Cpg) extends ForkJoinParallelCpgPass[Call](cpg) {

  extension (cpg: Cpg) {
    private def resolvedImports: Iterator[Call] =
      cpg.file.ast.isImportCall
        .filter(_.tag.map(_.name).exists(LinkCrossModuleVariableUsages.SUPPORTED_TAGS))
  }

  extension (call: Call) {
    private def resultAssignedTo: Iterator[Identifier] =
      call.inAssignment.assignedIdentifier

    private def importResolutions: Iterator[(String, String)] =
      call.start.isImportCall.flatMap(_.tag.map(tag => tag.name -> tag.value))
  }

  extension (str: String) {
    private def fromBase64: String =
      new String(Base64.getDecoder.decode(str.getBytes), StandardCharsets.UTF_8)
  }
  
  override def generateParts(): Array[Call] = cpg.resolvedImports.toArray

  override def runOnPart(builder: DiffGraphBuilder, imp: Call): Unit =
    val assignmentTarget = imp.resultAssignedTo.head
    val importUsages = assignmentTarget.ddgOut.l

    imp.importResolutions.foreach {
      // Add DDG links for `from module import variable` imports.
      case EvaluatedImport.RESOLVED_MEMBER -> memberSpec =>
        unpackMemberSpec(memberSpec) match {
          case (path, name) =>
            val sourceMembers = cpg.method.fullName(path).ast.isIdentifier.name(name).l
            sourceMembers.foreach(source => importUsages.foreach(target =>
              builder.addEdge(source, target, EdgeTypes.REACHING_DEF, PropertyNames.VARIABLE, source.name)
            ))
        }

      // Add DDG links for `import module … module.variable` imports.
      case EvaluatedImport.RESOLVED_TYPE_DECL -> module =>
        val memberAccesses = importUsages.astParent.fieldAccess.l
        val sourceModuleMember = cpg.method.fullName(module).ast.isIdentifier.l

        memberAccesses.foreach(target =>
          val memberNameOpt = target.argument(2).filter(_.isFieldIdentifier).map(_.code).headOption
          val memberDefinitions = memberNameOpt.map(memberName => sourceModuleMember.name(memberName).l).getOrElse(Nil)
          memberDefinitions.foreach(source =>
            builder.addEdge(source, target, EdgeTypes.REACHING_DEF, PropertyNames.VARIABLE, s"${assignmentTarget.code}.${target.code}")
          )
        )

      case _ => // ignore
    }

  private def unpackMemberSpec(memberSpec: String): (String, String) =
    memberSpec.split(",") match {
      case Array("BASE_PATH", path_b64, "NAME", name_b64) =>
        path_b64.fromBase64 -> name_b64.fromBase64
    }
}
