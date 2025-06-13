package matcher

import io.shiftleft.codepropertygraph.Cpg
import io.shiftleft.semanticcpg.language.*
import better.files.File
import io.joern.dataflowengineoss.layers.dataflows.{OssDataFlow, OssDataFlowOptions}
import io.joern.pysrc2cpg.*
import io.joern.x2cpg.X2Cpg
import io.joern.x2cpg.passes.base.AstLinkerPass
import io.joern.x2cpg.passes.callgraph.NaiveCallLinker
import io.joern.x2cpg.passes.frontend.XTypeRecoveryConfig
import io.shiftleft.semanticcpg.layers.LayerCreatorContext
import matcher.matching.MarkDependencyPatternPass
import matcher.postprocessing.*
import matcher.propagating.PropagateDependencyTagsPass
import matcher.traversals.*

class DependencyPatternMatcher {

  def run(projectPath: String, basePath: String): Map[String, Set[String]] =
    val cpg = createCpg(projectPath, basePath)
    new MarkDependencyPatternPass(cpg).createAndApply()

    // Fixpoint iteration to propagate tags
    var oldSize = 0
    var it = 0
    while (oldSize != cpg.size) {
      oldSize = cpg.size
      it += 1
      new PropagateDependencyTagsPass(cpg).createAndApply()
    }

    cpg.tag(DependencyTag.TAG_KEY).method.dedup.flatMap(m =>
      val tags = m.dependencyTags
      val location = m.fullName
      tags.toSet.map(location -> _)
    ).groupMap(_._1)(_._2).view.mapValues(_.toSet).toMap

  private def createCpg(projectPath: String, basePath: String) = {
    // Temporarily copy the source to a directory with the correct directory structure, to properly
    // resolve imports
    var cpg: Cpg = null
    File.usingTemporaryDirectory() { tmpDir =>
      val baseDirectory = tmpDir / basePath
      baseDirectory.createDirectories()
      File(projectPath).copyTo(baseDirectory)

      val config = Py2CpgOnFileSystemConfig().withInputPath(tmpDir.toString)
      val frontend = new Py2CpgOnFileSystem()
      cpg = frontend.createCpg(config).get
      val context = new LayerCreatorContext(cpg)

      val layerCreators = X2Cpg.defaultOverlayCreators() ++ List(new OssDataFlow(new OssDataFlowOptions()))
      layerCreators.foreach(_.create(context))
      applyPostProcessingPasses(cpg)
    }
    cpg
  }

  // From https://github.com/joernio/joern/blob/078d1c56168166a7682b1514962f20d99aba85d0/console/src/main/scala/io/joern/console/cpgcreation/PythonSrcCpgGenerator.scala#L29
  private def applyPostProcessingPasses(cpg: Cpg): Unit = {
    new RewriteRelativeImportsPass(cpg).createAndApply()
    new PythonImportResolverPass(cpg).createAndApply()
    new DynamicTypeHintFullNamePass(cpg).createAndApply()
    new PythonInheritanceNamePassFixed(cpg).createAndApply()
    val typeRecoveryConfig = XTypeRecoveryConfig()
    new PythonTypeRecoveryPassGenerator(cpg, typeRecoveryConfig).generate().foreach(_.createAndApply())
    new LinkInheritanceAfterTypeRecoveryPass(cpg).createAndApply()
    new LinkSelfCallsPass(cpg).createAndApply()
    new PythonTypeHintCallLinker(cpg).createAndApply()
    new NaiveCallLinker(cpg).createAndApply()

    // Some of passes above create new methods, so, we
    // need to run the ASTLinkerPass one more time
    new AstLinkerPass(cpg).createAndApply()

    // joern doesn't seem to link module-level variables defined in one module to the usages in other modules, but
    // we need that to identify certain types of guarded imports. We'll link these via DDG edges in a post-processing
    // pass.
    new LinkCrossModuleVariableUsages(cpg).createAndApply()
    new LinkNonLiteralModuleVariablesPass(cpg).createAndApply()

    // Joern also doesn't link superclass calls, which can lead to issues with propagation if subclassing is used
    new LinkExplicitSuperCallsPass(cpg).createAndApply()
    new LinkImplicitSuperCallsPass(cpg).createAndApply()
  }
}
