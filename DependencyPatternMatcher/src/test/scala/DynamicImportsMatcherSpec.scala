import matcher.DependencyPatternMatcher

class DynamicImportsMatcherSpec extends BaseSpec {
  it should "match dynamic imports with qualified importlib" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
      """
        |import importlib
        |
        |def do_stuff():
        |  importlib.import_module("lib")
        |  # Other stuff
        |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |from module_utils.util import do_stuff
        |
        |def main():
        |  module = AnsibleModule({})
        |  do_stuff()
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("DynamicImport:lib"))
  }

  it should "match dynamic imports with unqualified function name" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
      """
        |from importlib import import_module
        |
        |def do_stuff():
        |  import_module("lib")
        |  # Other stuff
        |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |
        |from module_utils.util import do_stuff
        |
        |def main():
        |  module = AnsibleModule({})
        |  do_stuff()
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("DynamicImport:lib"))
  }
}