"""Build on the target OS. Runtimes are resolved from the build environment."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build' / 'native'


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    browsers = BUILD / 'browsers'
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(browsers)
    subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--onedir', '--name', 'Zhenxia', '--paths', str(ROOT),
               '--collect-all', 'zhenxia', '--collect-all', 'playwright',
               '--collect-all', 'yt_dlp', '--collect-all', 'yt_dlp_ejs',
               '--collect-all', 'uvicorn']
    # The upstream package exposes these top-level modules and loads strategy code dynamically.
    for module in ('auth', 'config', 'control', 'core', 'storage', 'utils', 'gmssl'):
        command += ['--collect-all', module]
    for tool in ('ffmpeg', 'ffprobe', 'node'):
        executable = shutil.which(tool)
        if not executable:
            raise RuntimeError('Install build dependency: ' + tool)
        command += ['--add-binary', str(Path(executable).resolve()) + os.pathsep + 'bin']
    command.append(str(ROOT / 'packaging' / 'entrypoint.py'))
    subprocess.run(command, cwd=ROOT, check=True)
    destination = ROOT / 'dist' / 'Zhenxia'
    # Preserve Chromium's signed app/framework bundles. PyInstaller's binary
    # reclassification would strip their structure before ad-hoc signing on macOS.
    shutil.copytree(browsers, destination / '_internal' / 'browsers', symlinks=True)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md', 'README.zh-CN.md'):
        shutil.copy2(ROOT / name, destination / name)
    notices = destination / 'runtime-notices'
    notices.mkdir(exist_ok=True)
    with (notices / 'ffmpeg-license.txt').open('w') as stream:
        subprocess.run([shutil.which('ffmpeg'), '-L'], stdout=stream, stderr=stream, check=True)
    with (notices / 'ffmpeg-build.txt').open('w') as stream:
        subprocess.run([shutil.which('ffmpeg'), '-version'], stdout=stream, stderr=stream, check=True)
    node_license = Path(shutil.which('node')).resolve().parent.parent / 'LICENSE'
    if node_license.is_file():
        shutil.copy2(node_license, notices / 'node-LICENSE.txt')
    # Preserve wheel license notices for the redistributed Python dependencies.
    import importlib.metadata
    for distribution in importlib.metadata.distributions():
        for file in distribution.files or []:
            if '.dist-info/' in str(file) and any(word in file.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = notices / distribution.metadata['Name'] / file
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    if sys.platform == 'darwin':
        launcher = destination / 'Start Zhenxia.command'
        launcher.write_text('#!/bin/sh\ncd "$(dirname "$0")"\nexec ./Zhenxia\n')
        launcher.chmod(0o755)
    elif sys.platform == 'win32':
        (destination / 'Start Zhenxia.bat').write_text('@echo off\r\ncd /d "%~dp0"\r\nZhenxia.exe\r\nif errorlevel 1 pause\r\n')
    else:
        launcher = destination / 'start-zhenxia.sh'
        launcher.write_text('#!/bin/sh\ncd "$(dirname "$0")"\nexec ./Zhenxia\n')
        launcher.chmod(0o755)


if __name__ == '__main__':
    main()
