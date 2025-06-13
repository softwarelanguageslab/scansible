import matcher.DependencyPatternMatcher

class CommunityGeneralCmdRunnerMatcherSpec  extends BaseSpec {
  it should "match CmdRunner usage in plugin" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |from ansible_collections.community.general.plugins.module_utils.cmd_runner import CmdRunner
        |
        |def main():
        |  module = AnsibleModule({})
        |  runner = CmdRunner(module, "cmd")
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("CommunityGeneralCmdRunner:cmd"))
  }

  it should "match CmdRunner usage in plugin with kwarg" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |from ansible_collections.community.general.plugins.module_utils.cmd_runner import CmdRunner
        |
        |def main():
        |  module = AnsibleModule({})
        |  runner = CmdRunner(module, check_rc=False, command="cmd")
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("CommunityGeneralCmdRunner:cmd"))
  }

  it should "match CmdRunner usage in module_utils" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
      """
        |from ansible_collections.community.general.plugins.module_utils.cmd_runner import CmdRunner
        |
        |def do_stuff(module):
        |  runner = CmdRunner(module, "cmd")
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
        |  do_stuff(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("CommunityGeneralCmdRunner:cmd"))
  }
}