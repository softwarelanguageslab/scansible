package matcher.matching

import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.passes.CpgPass
import overflowdb.*

class MarkDependencyPatternPass(cpg: Cpg) extends CpgPass(cpg) {

  private def allMarkers: Seq[DependencyMatcher] =
    List(GuardedImportMatcher, DynamicImportMatcher, CommunityGeneralDepsMatcher, GetBinPathMatcher, CommunityGeneralCmdRunnerMatcher)

  override def run(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    allMarkers.foreach(_.mark(cpg))
}
