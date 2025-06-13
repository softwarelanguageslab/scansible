package matcher.matching

import io.shiftleft.codepropertygraph.generated.Cpg
import overflowdb.BatchedUpdate

trait DependencyMatcher {
  def mark(cpg: Cpg)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit
}
