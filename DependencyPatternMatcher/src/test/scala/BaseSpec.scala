import better.files.File
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should

trait BaseSpec extends AnyFlatSpec with should.Matchers {
  def withDirectory(test: File => Any): Unit = {
    File.usingTemporaryDirectory("test-")(test)
  }

  def withModuleUtils(test: File => Any): Unit = {
    withDirectory { tempDir =>
      (tempDir / "module_utils").createDirectory()
      (tempDir / "module_utils" / "__init__.py").createFile()
      test(tempDir)
    }
  }
}
