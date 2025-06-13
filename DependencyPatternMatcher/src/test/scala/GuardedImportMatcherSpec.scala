import better.files.File
import matcher.DependencyPatternMatcher

class GuardedImportMatcherSpec extends BaseSpec {
  val GUARDED_IMPORT_CODE: String =
    """
      |HAS_LIB = True
      |try:
      |  import lib
      |except ImportError:
      |  HAS_LIB = False""".stripMargin

  def withModuleUtilsHelperFunction(test: File => Any): Unit = {
    withModuleUtils { dir =>
      (dir / "module_utils" / "util.py").write(
        s"""
           |from ansible.module_utils.basic import missing_required_lib
           |
           |$GUARDED_IMPORT_CODE
           |
           |def check_has_lib(module):
           |  if not HAS_LIB:
           |    module.fail_json(missing_required_lib("lib"))
           |""".stripMargin)
      test(dir)
    }
  }

  def withModuleUtilsFlag(test: File => Any): Unit = {
    withModuleUtils { dir =>
      (dir / "module_utils" / "util.py").write(GUARDED_IMPORT_CODE)
      test(dir)
    }
  }

  it should "match guarded imports in single plugin.py:<module>.main" in withDirectory { dir =>
    (dir / "plugin.py").write(
      s"""
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |$GUARDED_IMPORT_CODE
        |
        |def main():
        |  module = AnsibleModule({})
        |
        |  if not HAS_LIB:
        |    module.fail_json(missing_required_lib("lib"))
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports variant which returns based on flag" in withDirectory { dir =>
    (dir / "plugin.py").write(
      s"""
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |$GUARDED_IMPORT_CODE
        |
        |def check_libs(module):
        |  if not HAS_LIB:
        |    return
        |
        |  module.fail_json("no lib")
        |
        |def main():
        |  module = AnsibleModule({})
        |
        |  check_libs(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports with conjunction conditions" in withDirectory { dir =>
    (dir / "plugin.py").write(
      s"""
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |$GUARDED_IMPORT_CODE
        |
        |HAS_LIB2 = True
        |try:
        |  import lib2
        |except:
        |  HAS_LIB2 = False
        |
        |def main():
        |  module = AnsibleModule({})
        |
        |  if not HAS_LIB or not HAS_LIB2:
        |    raise Error("problem")
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib", "GuardedImport:lib2"))
  }

  it should "match guarded imports variation where flag is not set in exception block" in withDirectory { dir =>
    (dir / "plugin.py").write(
      s"""
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |HAS_LIB = False
        |try:
        |  import lib
        |  HAS_LIB = True
        |except ImportError:
        |  pass
        |
        |def main():
        |  module = AnsibleModule({})
        |
        |  if not HAS_LIB:
        |    raise Error("problem")
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports checked in superclass" in withDirectory { dir =>
    (dir / "plugin.py").write(s"""
        |from ansible.module_utils.basic import AnsibleModule
        |
        |$GUARDED_IMPORT_CODE
        |
        |class Thing:
        |  def __init__(self):
        |    if not HAS_LIB:
        |      raise Error("no lib")
        |
        |class SubThing(Thing):
        |  def __init__(self):
        |    super().__init__()
        |
        |def main():
        |  module = AnsibleModule({})
        |  SubThing()
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports checked in superclass without explicit super call" in withDirectory { dir =>
    (dir / "plugin.py").write(s"""
        |from ansible.module_utils.basic import AnsibleModule
        |
        |$GUARDED_IMPORT_CODE
        |
        |class Thing:
        |  def __init__(self):
        |    if not HAS_LIB:
        |      raise Error("no lib")
        |
        |class SubThing(Thing):
        |  def do_specific_thing(self):
        |    print("hello world")
        |
        |def main():
        |  module = AnsibleModule({})
        |  thing = SubThing()
        |  thing.do_specific_thing()
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "not match tried imports without failure" in withDirectory { dir =>
    (dir / "plugin.py").write(s"""
        |from ansible.module_utils.basic import AnsibleModule
        |
        |try:
        |  from time import monotonic
        |except ImportError:
        |  from time import clock as monotonic
        |
        |def main():
        |  module = AnsibleModule({})
        |
        |  monotonic.do_stuff()
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should be (empty)
  }

  it should "match guarded imports with helper function in module_utils with unqualified call" in withModuleUtilsHelperFunction { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils.util import check_has_lib
        |
        |def main():
        |  module = AnsibleModule({})
        |  check_has_lib(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports with helper function in module_utils with qualified call" in withModuleUtilsHelperFunction { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils import util
        |
        |def main():
        |  module = AnsibleModule({})
        |  util.check_has_lib(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  // import module_utils.util doesn't get resolved properly, but we don't expect this to occur often
  ignore should "match guarded imports with helper function in module_utils with fully-qualified call" in withModuleUtilsHelperFunction { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |import module_utils.util
        |
        |def main():
        |  module = AnsibleModule({})
        |  module_utils.util.check_has_lib(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports where variable is assigned result of method call" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
      s"""
         |from ansible.module_utils.basic import missing_required_lib
         |import traceback
         |
         |try:
         |  import lib
         |except ImportError:
         |  LIB_IMPORTERROR = traceback.format_exc()
         |else:
         |  LIB_IMPORTERROR = None
         |
         |def check_has_lib():
         |  if LIB_IMPORTERROR is not None:
         |    module.fail_json(missing_required_lib("lib"), exception=LIB_IMPORTERROR)
         |
         |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils import util
        |
        |def main():
        |  module = AnsibleModule({})
        |  util.check_has_lib(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "not match guarded imports with helper function in module_utils if helper not called" in withModuleUtilsHelperFunction { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils.util import check_has_lib
        |
        |def main():
        |  module = AnsibleModule({})
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should not contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports with flag imported from module_utils with unqualified import" in withModuleUtilsFlag { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |from module_utils.util import HAS_LIB
        |
        |def main():
        |  module = AnsibleModule({})
        |  if not HAS_LIB:
        |    module.fail_json(missing_required_lib("lib"))
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  it should "match guarded imports with flag imported from module_utils with qualified import" in withModuleUtilsFlag { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |from module_utils import util
        |
        |def main():
        |  module = AnsibleModule({})
        |  if not util.HAS_LIB:
        |    module.fail_json(missing_required_lib("lib"))
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }

  // `import module_utils.util … module_utils.util.flag` doesn't get resolved properly yet, but we do not expect
  // to see this pattern occur very often.
  ignore should "match guarded imports with flag imported from module_utils with fully-qualified import" in withModuleUtilsFlag { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |import module_utils.util
        |
        |def main():
        |  module = AnsibleModule({})
        |  if not module_utils.util.HAS_LIB:
        |    module.fail_json(missing_required_lib("lib"))
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GuardedImport:lib"))
  }
}
