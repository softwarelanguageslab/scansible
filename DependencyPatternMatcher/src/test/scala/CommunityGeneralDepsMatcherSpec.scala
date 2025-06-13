import matcher.DependencyPatternMatcher

class CommunityGeneralDepsMatcherSpec extends BaseSpec {
  it should "match deps imports in plugin" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |from ansible_collections.community.general.plugins.module_utils import deps
        |
        |with deps.declare("lib"):
        |  import lib
        |
        |def main():
        |  module = AnsibleModule({})
        |  deps.validate(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("CommunityGeneralDeps:lib"))
  }

  it should "match multiple context manager imports in plugin" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule, missing_required_lib
        |from ansible_collections.community.general.plugins.module_utils import deps
        |
        |with deps.declare("lib"), deps.declare("other-lib"):
        |  import lib
        |  import other_lib
        |
        |def main():
        |  module = AnsibleModule({})
        |  deps.validate(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("CommunityGeneralDeps:lib", "CommunityGeneralDeps:other_lib"))
  }

  it should "match deps imports in module_utils" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
      """
        |from ansible_collections.community.general.plugins.module_utils import deps
        |
        |with deps.declare("lib"):
        |  import lib
        |
        |def do_stuff(module):
        |  deps.validate(module)
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

    result should contain ("plugin.py:<module>.main" -> Set("CommunityGeneralDeps:lib"))
  }
}