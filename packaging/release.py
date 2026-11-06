"""Validate version tags and publish only complete native package sets."""
import argparse
import hashlib
import re
import subprocess
import tomllib
from pathlib import Path

from packaging.version import Version

TARGETS = {
    'windows-x64': '.zip',
    'macos-x64': '.tar.gz',
    'macos-arm64': '.tar.gz',
    'linux-x64': '.tar.gz',
    'linux-arm64': '.tar.gz',
}


def validate_tag(tag, root):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-?(?:alpha|beta|rc)\.?\d+)?', tag):
        raise ValueError('Use vX.Y.Z or vX.Y.Z-rc.N version tags')
    version = Version(tag[1:])
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    if version != Version(project['project']['version']):
        raise ValueError('Tag version must match pyproject.toml')
    namespace = {}
    exec((root / 'zhenxia' / '__init__.py').read_text(encoding='utf-8'), namespace)
    if version != Version(namespace['__version__']):
        raise ValueError('Tag version must match zhenxia.__version__')
    return version


def publish(tag, root, directory, repository):
    version = validate_tag(tag, root)
    assets = [directory / ('Zhenxia-' + target + extension)
              for target, extension in TARGETS.items()]
    if not all(asset.is_file() and asset.stat().st_size > 0 for asset in assets):
        raise ValueError('Release requires all five tested platform archives')
    checksums = directory / 'SHA256SUMS.txt'
    lines = []
    for asset in assets:
        digest = hashlib.sha256()
        with asset.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        lines.append(digest.hexdigest() + '  ' + asset.name)
    checksums.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    command = ['gh', 'release', 'create', tag, *map(str, assets), str(checksums),
               '--repo', repository, '--verify-tag', '--generate-notes',
               '--title', 'Zhenxia ' + tag,
               '--notes', 'Extract the complete archive and run the platform launcher. '
               'Unsigned preview packages; Linux requires Chromium system libraries. '
               'See README for usage. / 完整解压后运行启动文件，使用说明见 README。']
    if version.is_prerelease:
        command += ['--prerelease', '--latest=false']
    # gh uploads into a draft before publishing. Failed uploads leave a draft for recovery.
    # Existing published releases are never overwritten; retries fail instead of changing assets.
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--repo')
    args = parser.parse_args()
    validate_tag(args.tag, args.root)
    if args.assets:
        if not args.repo:
            parser.error('--repo is required when publishing')
        publish(args.tag, args.root, args.assets, args.repo)


if __name__ == '__main__':
    main()
