import sys
import os
import urllib.request
import subprocess
import tarfile
import winreg

from contextlib import contextmanager
from argparse import ArgumentParser
from logging import Formatter, getLogger, StreamHandler, DEBUG
logger = getLogger(__name__)
logger.setLevel(DEBUG)

'''
downloads
    + zlib-1.2.8.tar.xz

work
    + zlib-1.2.8
    + zlib-1.2.8_build

prefix_x86
    + bin
    + include
    + libs
'''

def get_vsdir(version="15.0"):
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE
            , "SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\SxS\\VS7") as key:
        return winreg.QueryValueEx(key, '15.0')[0]

def get_cmake():
    return os.path.join(get_vsdir()
            , "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe")

def get_msbuild():
    return os.path.join(get_vsdir()
            , "MSBuild/15.0/bin/msbuild.exe")

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE
            , "SOFTWARE\\WOW6432Node\\Microsoft\\MSBuild\\14.0") as key:
        msbuild_dir=winreg.QueryValueEx(key, 'MSBuildOverrideTasksPath')[0]
        return os.path.join(msbuild_dir, 'msbuild.exe')


def exec_subprocess(cmd):
    logger.info(':execute: %s', ' '.join(cmd))
    proc = subprocess.Popen(cmd
            , shell=True
            , stdout=subprocess.PIPE
            , stderr=subprocess.STDOUT)

    while True:
        line = proc.stdout.readline()
        if line:
            logger.debug(line.rstrip().decode('cp932'))

        if not line and proc.poll() is not None:
            break

    if proc.returncode!=0:
        raise Exception(proc.returncode)


class Package:
    def __init__(self, url, archive_name=None):
        self.url=url
        if archive_name:
            self.archive_name=archive_name
        else:
            self.archive_name=os.path.basename(url)

    def _is_git(self):
        return False
    is_git = property(_is_git)

    def _archive_path(self):
        return 'downloads/%s' % self.archive_name
    archive_path=property(_archive_path)

    def _extract_dirname(self):
        if self.archive_name.endswith('.tar.xz'):
            return self.archive_name[0:-7]
        if self.archive_name.endswith('.tar.gz'):
            return self.archive_name[0:-7]
        if self.archive_name.endswith('.tar.bz2'):
            return self.archive_name[0:-8]
        #
        return os.path.splitext(self.archive_name)[0]
    extract_dirname=property(_extract_dirname)

    def _build_type(self):
        return 'cmake'
    build_type=property(_build_type)

g_packages=[
        Package('http://zlib.net/zlib-1.2.11.tar.xz'),
        Package('http://download.savannah.nongnu.org/releases/openexr/ilmbase-2.2.0.tar.gz'),
        Package('http://prdownloads.sourceforge.net/libpng/libpng-1.6.29.tar.xz?download'
            , 'libpng-1.6.29.tar.xz')
        ]

def get_package(name):
    for p in g_packages:
        if name in p.url:
            return p


@contextmanager
def pushpopd(dst):
    current=os.getcwd()
    try:
        os.chdir(dst)
        logger.debug('cwd %s', os.getcwd())
        yield
    except Exception as ex:
        logger.error(ex)
    finally:
        os.chdir(current)
        logger.debug('cwd %s', os.getcwd())

def extract(archive, dst):
    logger.debug('extract %s', archive)
    tf = tarfile.open(archive, 'r')
    tf.extractall(dst)

def cmake_build(package, args):
    prefix=os.path.abspath(args.prefix)
    logger.info('cmake_build %s to %s', package, prefix)
    work_dir='work/%s_build_%s' % (package.extract_dirname, args.arch)
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)
    with pushpopd(work_dir):
        if os.path.exists('CMakeCache.txt'):
            os.remove('CMakeCache.txt')
        cmake=get_cmake()
        cmd=[cmake
                , '-G'
                , 'Visual Studio 15 2017'
                , '-DCMAKE_INSTALL_PREFIX=%s' % prefix
                , '-DZLIB_ROOT=%s' % prefix
                , '-DCMAKE_PREFIX_PATH=%s' % prefix
                , '-DCMAKE_FIND_DEBUG_MODE=1'
                , '../%s' % package.extract_dirname
                ]
        if "uwp" in args.arch:
            cmd.append('-DCMAKE_SYSTEM_NAME=WindowsStore')
            cmd.append('-DCMAKE_SYSTEM_VERSION=10.0')
        try:
            exec_subprocess(cmd)
        except Exception as ex:
            logger.error(ex)
            sys.exit(1)

        cmd=[get_msbuild()
                , 'Install.vcxproj'
                , '/p:Configuration=Release'
                ]
        try:
            exec_subprocess(cmd)
        except Exception as ex:
            logger.error(ex)
            sys.exit(1)


class Download:
    @staticmethod
    def execute(package):
        if os.path.exists(package.archive_path):
            logger.debug('%s exists', package.archive_path)
            return

        logger.info('download %s', package.url)

        archive_dir=os.path.dirname(package.archive_path)
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
        urllib.request.urlretrieve(package.url, package.archive_path)


class Extract:
    @staticmethod
    def execute(package):
        extract_dir='work/%s' % package.extract_dirname
        if os.path.exists(extract_dir):
            logger.debug('%s exists', extract_dir)
            return

        if not os.path.exists(package.archive_path):
            Download.execute(package)

        extract(package.archive_path, 'work')
        

class Build:
    @staticmethod
    def execute(args):
        package=get_package(args.package)
        logger.info('build %s', package)

        if package.is_git:
            raise NotImplementedError()
        else:
            Extract.execute(package)

        if package.build_type=='cmake':
            cmake_build(package, args)
        else:
            raise NotImplementedError()


g_commands=[Build()]


def get_command(command):
    for c in g_commands:
        if c.__name__.lower()==command.lower():
            return c


if __name__=="__main__":
    formatter = Formatter('%(asctime)-15s - %(levelname)-8s - %(message)s')
    handler = StreamHandler(sys.stdout)
    handler.setLevel(DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    parser=ArgumentParser()
    subparsers = parser.add_subparsers(help='commands', dest='command')
    build_parser = subparsers.add_parser('build', help='build package')
    build_parser.add_argument('package', action='store', help='target package')
    build_parser.add_argument('--arch', action='store'
            , help='x32, x64, uwp32, uwp64'
            , default='x32')
    build_parser.add_argument('--config', action='store'
            , help='debug, release'
            , default='release'
            )
    build_parser.add_argument('--prefix', action='store'
            , help='install destination'
            )

    args=parser.parse_args()

    if args.command and not args.prefix:
        drive=os.getcwd()[0:2]
        args.prefix="%s/usr_%s" % (drive, args.arch)

    if args.command=='build':
        Build.execute(args)
    else:
        parser.print_help()

