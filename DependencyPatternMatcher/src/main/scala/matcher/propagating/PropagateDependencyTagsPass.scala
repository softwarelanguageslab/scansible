package matcher.propagating

import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.Method
import io.shiftleft.passes.{CpgPass, ForkJoinParallelCpgPass}
import io.shiftleft.semanticcpg.language.*
import matcher.DependencyTag
import matcher.traversals.*
import overflowdb.BatchedUpdate

class PropagateDependencyTagsPass(cpg: Cpg) extends ForkJoinParallelCpgPass[nodes.Method](cpg) {

  extension (method: nodes.Method) {
    private def callersWithKnownReceiver: Iterator[nodes.Method] =
      method.callIn
        .filter(c => c.methodFullName != "<unknownFullName>" || c.dynamicTypeHintFullName.contains(method.fullName))
        .method.dedup

    private def approximatedCallers: Iterator[nodes.Method] =
      val knownCallers = method.callersWithKnownReceiver.toSet
      method.callIn.method.filterNot(knownCallers.contains)

    private def isFakeMethod: Boolean =
      method.name.endsWith("<fakeNew>")
  }

  override def generateParts(): Array[Method] = cpg.tag(DependencyTag.TAG_KEY).method.dedup.toArray

  override def runOnPart(implicit builder: DiffGraphBuilder, m: Method): Unit =
    // Only propagate to callers where the receiver type is known. If joern has too little type information,
    // it'll over-approximate calls based on the method name, which can lead to many false positives for
    // methods with generic names, like "run".
    /*m.approximatedCallers.filterNot(_.isFakeMethod)
      .foreach(caller =>
        println(s"Not propagating ${m.dependencyTags.l} from ${m.fullName} to ${caller.fullName}"))*/
    val callerMethods = m.callersWithKnownReceiver.l

    m.dependencyTags.foreach(t => {
      val callersWithoutTag = callerMethods.filterNot(_.dependencyTags.contains(t)).l
      /* callersWithoutTag.foreach(c =>
        println(s"Propagating $t from ${m.fullName} to ${c.fullName}"))*/
      callersWithoutTag.newTagNodePair(DependencyTag.TAG_KEY, t).store()
    })
}
