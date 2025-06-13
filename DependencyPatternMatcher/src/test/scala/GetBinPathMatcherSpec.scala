import matcher.DependencyPatternMatcher

class GetBinPathMatcherSpec extends BaseSpec {
  it should "match module.get_bin_path in plugin" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |def main():
        |  module = AnsibleModule({})
        |  module.get_bin_path("cmd")
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }

  it should "match non-module get_bin_path in plugin" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |from ansible.module_utils.common.process import get_bin_path
        |
        |def main():
        |  module = AnsibleModule({})
        |  get_bin_path("cmd")
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }

  it should "match get_bin_path with constant variable argument" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |def main():
        |  module = AnsibleModule({})
        |  cmd = "apt"
        |  module.get_bin_path(cmd)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:apt"))
  }

  it should "not match get_bin_path with non-constant variable argument" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |def main():
        |  module = AnsibleModule({})
        |  if os == "debian":
        |    cmd = "apt"
        |  else:
        |    cmd = "test"
        |  module.get_bin_path(cmd)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should be (empty)
  }

  it should "match get_bin_path with constant module variable argument" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |COMMAND_NAME = "apt"
        |
        |def main():
        |  module = AnsibleModule({})
        |  module.get_bin_path(COMMAND_NAME)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:apt"))
  }

  it should "match get_bin_path in class initializer" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |class Thing:
        |  def __init__(self, module):
        |    self.cmd = module.get_bin_path("cmd")
        |
        |def main():
        |  module = AnsibleModule({})
        |  Thing(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }

  it should "match get_bin_path in with constant class var argument" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |class Thing:
        |  cmd_name = "apt"
        |
        |  def __init__(self, module):
        |    self.cmd = module.get_bin_path(Thing.cmd_name)
        |
        |def main():
        |  module = AnsibleModule({})
        |  Thing(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:apt"))
  }

  it should "match get_bin_path in with constant instance var argument" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |class Thing:
        |  cmd_name = "apt"
        |
        |  def __init__(self, module):
        |    self.cmd = module.get_bin_path(self.cmd_name)
        |
        |def main():
        |  module = AnsibleModule({})
        |  Thing(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:apt"))
  }

  it should "match get_bin_path in with constant instance var argument assigned in method" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |class Thing:
        |  def __init__(self):
        |    self.cmd_name = "apt"
        |
        |  def check_available(self, module):
        |    self.cmd = module.get_bin_path(self.cmd_name)
        |
        |def main():
        |  module = AnsibleModule({})
        |  Thing().check_available(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:apt"))
  }

  it should "match get_bin_path in with constant class var argument accessed in class method" in withDirectory { dir =>
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |class Thing:
        |  cmd_name = "apt"
        |
        |  @classmethod
        |  def check_available(cls, module):
        |    module.get_bin_path(cls.cmd_name)
        |
        |def main():
        |  module = AnsibleModule({})
        |  Thing.check_available(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:apt"))
  }

  it should "match get_bin_path in module_utils function" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
        """
           |def do_stuff(module):
           |  module.get_bin_path("cmd")
           |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
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

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }

  it should "match get_bin_path in module_utils class initializer" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
        """
           |class Thing:
           |  def __init__(self, module):
           |    self.cmd = module.get_bin_path("cmd")
           |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils.util import Thing
        |
        |def main():
        |  module = AnsibleModule({})
        |  Thing(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }

  it should "match get_bin_path in module_utils class method" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
        """
           |class Thing:
           |  def __init__(self, module):
           |    pass
           |  def do_stuff(self):
           |    cmd = module.get_bin_path("cmd")
           |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils.util import Thing
        |
        |def main():
        |  module = AnsibleModule({})
        |  Thing(module).do_stuff()
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }

  // Subclassing call graphs don't seem to work properly in Joern at the moment, unsure if this pattern
  // variant occurs often
  it should "match get_bin_path in module_utils subclass" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
        """
           |class Thing:
           |  def __init__(self, module):
           |    self.cmd = module.get_bin_path("cmd")
           |
           |class SubThing(Thing):
           |  pass
           |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils.util import SubThing
        |
        |def main():
        |  module = AnsibleModule({})
        |  SubThing(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }

  it should "match get_bin_path in plugin subclass from module_utils class" in withModuleUtils { dir =>
    (dir / "module_utils" / "util.py").write(
        """
           |class Thing:
           |  def __init__(self, module):
           |    self.cmd = module.get_bin_path("cmd")
           |""".stripMargin)
    (dir / "plugin.py").write(
      """
        |from ansible.module_utils.basic import AnsibleModule
        |
        |from module_utils.util import Thing
        |
        |class SubThing(Thing):
        |  pass
        |
        |def main():
        |  module = AnsibleModule({})
        |  SubThing(module)
        |
        |if __name__ == "__main__":
        |  main()
        |""".stripMargin)

    val result = new DependencyPatternMatcher().run(dir.toString(), "")

    result should contain ("plugin.py:<module>.main" -> Set("GetBinPath:cmd"))
  }
}