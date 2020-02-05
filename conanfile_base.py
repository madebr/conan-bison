from conans import ConanFile, AutoToolsBuildEnvironment, tools
from conans.errors import ConanException
from contextlib import contextmanager
import glob
import os
import shutil


class ConanFileBase(ConanFile):
    _base_name = "bison"
    version = "3.3.2"
    url = "https://github.com/bincrafters/conan-bison"
    homepage = "https://www.gnu.org/software/bison/"
    description = "Bison is a general-purpose parser generator"
    topics = ("conan", "bison", "parser")
    license = "GPL-3.0-or-later"
    exports = ["LICENSE.md"]
    exports_sources = ["patches/*.patch"]
    requires = ("m4_installer/1.4.18@bincrafters/stable",)
    _autotools = None
    _source_subfolder = "source_subfolder"

    @property
    def _is_msvc(self):
        return self.settings.compiler == "Visual Studio"

    def build_requirements(self):
        if tools.os_info.is_windows:
            if "CONAN_BASH_PATH" not in os.environ:
                self.build_requires("msys2/20190524")
        if self._is_msvc:
            self.build_requires("automake_build_aux/1.16.1@bincrafters/stable")

    def source(self):
        source_url = "https://ftp.gnu.org/gnu/bison/"
        tools.get("{0}/{1}-{2}.tar.gz".format(source_url, "bison", self.version),
                  sha256="0fda1d034185397430eb7b0c9e140fb37e02fbfc53b90252fa5575e382b6dbd1")
        extracted_dir = "bison-" + self.version
        os.rename(extracted_dir, self._source_subfolder)

    def configure(self):
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

    @contextmanager
    def _build_context(self):
        with tools.vcvars(self.settings) if self._is_msvc else tools.no_op():
            yield

    def _configure_autotools(self):
        true = tools.which("true") or "/bin/true"
        true = tools.unix_path(true) if tools.os_info.is_windows else true
        args = ["HELP2MAN=%s" % true, "MAKEINFO=%s" % true, "--disable-nls"]
        build = None
        host = None
        if self._is_msvc:
            for filename in ["compile", "ar-lib"]:
                shutil.copy(os.path.join(self.deps_cpp_info["automake_build_aux"].rootpath, filename),
                            os.path.join(self._source_subfolder, "build-aux", filename))
            build = False
            if self.settings.arch == "x86":
                host = "i686-w64-mingw32"
            elif self.settings.arch == "x86_64":
                host = "x86_64-w64-mingw32"
            args.extend(['CC={}/build-aux/compile cl -nologo'.format(tools.unix_path(self._source_subfolder)),
                         'CXX={}/build-aux/compile cl -nologo'.format(tools.unix_path(self._source_subfolder)),
                         'CFLAGS=-{}'.format(self.settings.compiler.runtime),
                         'LD=link',
                         'NM=dumpbin -symbols',
                         'STRIP=:',
                         'AR={}/build-aux/ar-lib lib'.format(tools.unix_path(self._source_subfolder)),
                         'RANLIB=:',
                         "gl_cv_func_printf_directive_n=no"])
        if self._autotools:
            return self._autotools
        self._autotools = AutoToolsBuildEnvironment(self, win_bash=tools.os_info.is_windows)
        self._autotools.configure(args=args, build=build, host=host, configure_dir=self._source_subfolder)
        return self._autotools

    def build(self):
        for filename in sorted(glob.glob("patches/*.patch")):
            self.output.info('applying patch "%s"' % filename)
            tools.patch(base_path=self._source_subfolder, patch_file=filename)
        tools.replace_in_file(os.path.join(self._source_subfolder, "Makefile.in"),
                              "dist_man_MANS = $(top_srcdir)/doc/bison.1",
                              "dist_man_MANS =")
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "yacc.in"),
                              "@prefix@",
                              "${}_ROOT".format(self.name.upper()))
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "yacc.in"),
                              "@bindir@",
                              "${}_ROOT/bin".format(self.name.upper()))

        # Debug m4
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "getargs.c"),
                              "int trace_flag = trace_none;",
                              "int trace_flag = trace_m4;")

        with self._build_context():
            autotools = self._configure_autotools()
            autotools.make()

    @property
    def _os(self):
        try:
            return self.settings.os
        except ConanException:
            return self.settings.os_build

    def package(self):
        self.copy(pattern="COPYING", src=self._source_subfolder, dst="licenses")
        with self._build_context():
            autotools = self._configure_autotools()
            autotools.install()
        if self._is_msvc:
            shutil.move(os.path.join(self.package_folder, "lib", "liby.a"),
                        os.path.join(self.package_folder, "lib", "y.lib"))
        if self._os == "Windows":
            for root, _, files in os.walk(os.path.join(self.package_folder, "share")):
                for file in files:
                    if not file.endswith(".m4"):
                        continue
                    fn = os.path.join(root, file)
                    contents = open(fn, "rb").read()
                    open(fn, "wb").write(contents.replace(b"\n", b"\r\n"))

