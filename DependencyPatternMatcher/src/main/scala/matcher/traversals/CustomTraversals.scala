package matcher.traversals

import io.shiftleft.codepropertygraph.generated.*
import io.shiftleft.codepropertygraph.generated.nodes.*
import io.shiftleft.semanticcpg.language.*
import matcher.DependencyTag
import overflowdb.BatchedUpdate

extension (cpg: Cpg) {
  def size: Int = cpg.graph.nodeCount() + cpg.graph.edgeCount()
}

extension (node: StoredNode) {
  def dependencyTags: Iterator[String] = node.tag.filter(_.name == DependencyTag.TAG_KEY).map(_.value)
}

extension (node: Expression) {
  def ddgOut: Iterator[CfgNode] =
    node.outE(EdgeTypes.REACHING_DEF)
      .map(_.inNode)
      .collectAll[CfgNode]
}

extension (nodes: Traversal[Expression]) {
  def ddgOut: Iterator[CfgNode] = nodes.flatMap(_.ddgOut)
}

extension (lit: Literal) {
  def unpackedString: String =
    val packedStr = lit.code

    if (packedStr.startsWith("'") && packedStr.endsWith("'")) || (packedStr.startsWith("\"") && packedStr.endsWith("\"")) then
      packedStr.slice(1, packedStr.length - 1)
    else packedStr
}

extension (typeDecl: TypeDecl) {
  def superDefinedMethods: Iterator[Method] =
    typeDecl.baseTypeDecl.flatMap(_.definedMethods)

  def subDefinedMethods: Iterator[Method] =
    typeDecl.derivedTypeDecl.flatMap(_.definedMethods)

  def definedMethods: Iterator[Method] =
    typeDecl.method.name("<body>").astChildren.isMethod

  def allTransitiveDefinedMethods: Iterator[Method] =
    val ownM = typeDecl.definedMethods
    val superM = typeDecl.superDefinedMethodsTransitive
    val subM = typeDecl.subDefinedMethodsTransitive

    ownM ++ superM ++ subM

  def superDefinedMethodsTransitive: Iterator[Method] =
    typeDecl.baseTypeDeclTransitive.flatMap(_.definedMethods)

  def subDefinedMethodsTransitive: Iterator[Method] =
    typeDecl.derivedTypeDeclTransitive.flatMap(_.definedMethods)

  def superMethod(methodName: String): Iterator[Method] =
    val superM = superDefinedMethods.filter(_.name == methodName)
    if superM.nonEmpty then superM else typeDecl.baseTypeDecl.flatMap(_.superMethod(methodName))

  def fieldAssignments(fieldName: String): Iterator[Call] =
    val ownFields = getOwnFieldAssignments(fieldName)
    if ownFields.nonEmpty then ownFields else typeDecl.baseTypeDecl.flatMap(_.fieldAssignments(fieldName))

  def getOwnFieldAssignments(fieldName: String): Iterator[Call] =
    typeDecl.ast.assignment
      .filter(_.argument(1) match {
        case ident: Identifier => ident.name == fieldName
        case call: Call if call.isFieldAccess && call.argument(1).isIdentifier =>
          val assignmentReceiver = call.argument(1).asInstanceOf[Identifier]
          val assignedFieldName = call.argument(2).asInstanceOf[FieldIdentifier]

          // Assignment to own field
          (assignmentReceiver.name == "self" || assignmentReceiver.name == "cls" || assignmentReceiver.typeFullName == typeDecl.fullName)
          // and assignment to correct field
          && assignedFieldName.code == fieldName
        case _ => false
      }).dedup
}

extension (ast: Traversal[AstNode]) {
  def isImportCall: Iterator[Call] = ast.isCall.name("import")
}

extension (node: Traversal[CfgNode]) {
  def inCondition: Iterator[CfgNode] = node.inAst.isCfgNode.where(_.controls)
}

extension (node: Method) {
  def markDependency(dependencyType: DependencyTag, dependencies: IterableOnce[String])(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    dependencies.iterator.foreach(node.markDependency(dependencyType, _))

  def markDependency(dependencyType: DependencyTag, dependency: String)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    node.start.newTagNodePair(DependencyTag.TAG_KEY, s"$dependencyType:$dependency").store()
}

extension (node: Traversal[Method]) {
  def markDependency(dependencyType: DependencyTag, dependencies: IterableOnce[String])(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    val nodes = node.l
    dependencies.iterator.foreach(nodes.iterator.markDependency(dependencyType, _))

  def markDependency(dependencyType: DependencyTag, dependency: String)(implicit builder: BatchedUpdate.DiffGraphBuilder): Unit =
    node.newTagNodePair(DependencyTag.TAG_KEY, s"$dependencyType:$dependency").store()
}

extension (tryBlock: ControlStructure) {
  def exceptBranch: AstNode = tryBlock.astChildren.l(1)
}

extension (call: nodes.Call) {
  def isFieldAccess: Boolean =
    call.name == "<operator>.fieldAccess"

  def literalArgument(index: Int): Option[String] =
    call.literalArgument(_.arguments(index).headOption)

  def literalArgument(argGetter: Call => Option[Expression]): Option[String] =

    def getOneStringAssignment(assignments: List[Expression]): Option[String] =
      Iterator.single(assignments)
        .filter(_.size == 1)
        .map(_.head._reachingDefIn.collectAll[Literal].l)
        .filter(_.size == 1)
        .map(_.head)
        .filter(_.dynamicTypeHintFullName == Seq("builtin.str"))
        .map(_.unpackedString)
        .headOption

    val arg = argGetter(call)
    arg.flatMap {
      case lit: Literal =>
        Some(lit)
          .filter(_.dynamicTypeHintFullName == Seq("builtin.str"))
          .map(_.unpackedString)

      // Attempt to resolve an identifier to a single constant literal definition
      case ident: Identifier =>
        val definitions = ident
          .inE(EdgeTypes.REACHING_DEF)
          // Need to do additional filtering on the variable name in the reaching def edge, since def edges are also
          // linked for the rest of the arguments in the call.
          .filter(_.property(PropertyNames.VARIABLE) == ident.name)
          .map(_.outNode().get().ref)
          .collectAll[Identifier]
          .where(_.inAssignment).dedup.l
        Some(definitions)
          .flatMap(getOneStringAssignment)

      // Attempt to resolve a field access to a single constant literal definition
      case call: Call if call.isFieldAccess && call.argument(1).isIdentifier =>
        val receiver = call.argument(1).asInstanceOf[Identifier]
        val fieldName = call.argument(2).asInstanceOf[FieldIdentifier].code
        val containingClass = (receiver.typeFullName, receiver.name) match {
          case ("ANY", "self") | ("ANY", "cls") =>
            call.method.typeDecl
          case (typeName, _) if typeName != "object" && typeName != "ANY" =>
            receiver.graph.nodes.iterator.collectAll[TypeDecl].fullNameExact(typeName).headOption
          case _ => None
        }
        containingClass
          .map(_.fieldAssignments(fieldName).l)
          .flatMap(getOneStringAssignment)

      case _ => None
    }
}

extension (itCall: Traversal[nodes.Call]) {
  def importedLibrary: Traversal[String] = itCall.flatMap(call => {
    call.name match {
      case "import" =>
        val args = call.argument.toList
        // import a from b => import(b, a)
        // import b => import(<empty string>, b)
        val importedPackage = if args.head.code == "" then args(1) else args.head
        val lib = importedPackage.code.split("\\.").head
        // Ignore relative imports (e.g., from `..module_utils.util import something`), we can't extract the library
        // name from it.
        if lib.nonEmpty then Some(lib) else None
      case _ => None
    }
  })

  def assignedIdentifier: Traversal[Identifier] = itCall.flatMap(call =>
    call.name match {
      case "<operator>.assignment" =>
        call.argument(1).start.isIdentifier
      case _ => Nil
    })
}