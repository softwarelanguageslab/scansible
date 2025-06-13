package matcher.matching
import io.joern.dataflowengineoss.language.*
import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.semanticcpg.language.*
import matcher.DependencyTag
import matcher.traversals.*
import overflowdb.*

/** Mark methods that call `get_bin_path`. */
object GetBinPathMatcher extends DependencyMatcher {
  override def mark(cpg: Cpg)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    // We're not checking whether this is the correct function in depth. We could do this by filtering on whether
    // it is a function originating from the right Ansible file, or a method in the AnsibleModule class. However,
    // oftentimes, the `module` object is passed to a utility function, in which case we'll lose the type information,
    // and this filter will remove valid calls. Thus, we're over-approximating, but assume it won't be a problem in
    // practice.
    val getBinPathCalls = cpg.call("get_bin_path")
    getBinPathCalls
      .flatMap(c => c.literalArgument(1).map(c.method -> _))
      .foreach((m, lib) =>
        // println(s"Marking GetBinPath on ${m.fullName} of $lib")
        m.markDependency(DependencyTag.GetBinPath, lib)
      )
}
