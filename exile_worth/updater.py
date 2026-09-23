"""New versions: find them on GitHub Releases, download, verify, install.

Only a packaged build updates itself; from source, `git pull` does. The check
sends one anonymous request to the GitHub API and nothing else: no screenshot,
inventory or identifier leaves the machine. Every URL, including each redirect
of a download, is pinned to `UPDATE_HOSTS`.

The installer is the one `packaging/build.ps1` makes and the release workflow
publishes, beside a `.sha256` file; a download whose hash does not match that
file is deleted and never run.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__

REPOSITORY = 'SylvainRiom/exile-worth'
LATEST = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES = f'https://github.com/{REPOSITORY}/releases'
# github.com serves the download link and redirects it to its asset storage.
UPDATE_HOSTS = frozenset({'api.github.com', 'github.com', 'objects.githubusercontent.com',
                          'release-assets.githubusercontent.com'})
CHECK_INTERVAL = 24 * 3600
MAX_INSTALLER = 500_000_000
AGENT = f'ExileWorth/{__version__} (update check)'


def parse_version(text):
    """'v1.2.3' or '1.2.3' -> (1, 2, 3); anything else -> None."""
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', (text or '').strip())
    return tuple(int(part) for part in match.groups()) if match else None


def permitted(url):
    parts = urlparse(url)
    return parts.scheme == 'https' and parts.hostname in UPDATE_HOSTS


class UpdateError(Exception):
    """`key` is an i18n key under `update.error.*`, never displayed as is."""
    def __init__(self, key, detail=''):
        super().__init__(f'{key}: {detail}' if detail else key)
        self.key = key


class PinnedRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        if not permitted(url):
            raise UpdateError('host', url)
        return super().redirect_request(request, fp, code, message, headers, url)


_opener = build_opener(PinnedRedirects)


def open_url(url, timeout, accept='application/octet-stream'):
    if not permitted(url):
        raise UpdateError('host', url)
    return _opener.open(Request(url, headers={'User-Agent': AGENT, 'Accept': accept}), timeout=timeout)


@dataclass(frozen=True)
class Release:
    version: tuple
    tag: str
    installer_url: str
    installer_name: str
    installer_size: int
    checksum_url: str
    page_url: str

    @property
    def label(self):
        return '.'.join(map(str, self.version))


def release_from(data):
    """The installable release described by the API answer, or None.

    A release is installable only with both its installer and its checksum,
    named after its own version: a tag without them is ignored, not guessed.
    """
    version = parse_version(data.get('tag_name'))
    if version is None or data.get('draft') or data.get('prerelease'):
        return None
    label = '.'.join(map(str, version))
    assets = {asset.get('name'): asset for asset in data.get('assets') or []}
    name = f'ExileWorth-Setup-{label}.exe'
    installer, checksum = assets.get(name), assets.get(name + '.sha256')
    if not installer or not checksum:
        return None
    urls = installer.get('browser_download_url', ''), checksum.get('browser_download_url', '')
    if not all(permitted(url) for url in urls):
        return None
    page = data.get('html_url') or RELEASES
    return Release(version, data['tag_name'], urls[0], name, int(installer.get('size') or 0), urls[1],
                   page if permitted(page) else RELEASES)


def newer_release(current=__version__, fetch=None):
    """The latest release if it is newer than `current`, else None."""
    if fetch is None:
        def fetch():
            try:
                with open_url(LATEST, timeout=10, accept='application/vnd.github+json') as response:
                    return json.loads(response.read(1_000_000))
            except HTTPError as error:
                # No published release yet: nothing newer, not a failure.
                if error.code == 404:
                    return {}
                raise
    release = release_from(fetch())
    current = parse_version(current)
    return release if release and current and release.version > current else None


def expected_hash(text, name):
    """The hex digest from a `sha256sum`-style line naming `name` (or a bare digest)."""
    for line in text.splitlines():
        fields = line.split()
        if fields and re.fullmatch(r'[0-9a-fA-F]{64}', fields[0]) and (
                len(fields) == 1 or fields[-1].lstrip('*') == name):
            return fields[0].lower()
    raise UpdateError('checksum')


def download(release, directory, progress=None, opener=open_url):
    """Download the installer into `directory` and verify it. Returns its path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with opener(release.checksum_url, timeout=20) as response:
        expected = expected_hash(response.read(10_000).decode('ascii', 'replace'), release.installer_name)
    target = directory / release.installer_name
    partial = target.with_suffix('.part')
    digest, done = hashlib.sha256(), 0
    try:
        with opener(release.installer_url, timeout=30) as response, open(partial, 'wb') as file:
            total = int(response.headers.get('Content-Length') or release.installer_size or 0)
            while chunk := response.read(1 << 20):
                done += len(chunk)
                if done > MAX_INSTALLER:
                    raise UpdateError('size')
                digest.update(chunk)
                file.write(chunk)
                if progress:
                    progress(done, total)
        if digest.hexdigest() != expected:
            raise UpdateError('checksum')
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def clean(directory):
    """Remove installers left by a previous update; one still in use stays."""
    for file in Path(directory).glob('ExileWorth-Setup-*'):
        try:
            file.unlink()
        except OSError:
            pass


def install_command(installer, language='en'):
    # /RELAUNCH=1 is read by packaging/installer.iss to start the new version.
    return [str(installer), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS',
            '/RELAUNCH=1', f'/LANG={language}']


def start_install(installer, language='en'):
    """Start the installer detached; the caller then closes the app."""
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(install_command(installer, language), close_fds=True, creationflags=flags)


def enabled(environ=os.environ):
    """A packaged build checks; from source only with EXILE_UPDATE_CHECK=1.
    EXILE_UPDATE_CHECK=0 turns it off everywhere."""
    flag = environ.get('EXILE_UPDATE_CHECK')
    if flag is not None:
        return flag == '1'
    return bool(getattr(sys, 'frozen', False))


def due(stored, now=None):
    """Whether the daily automatic check should run, from the settings dict."""
    if stored.get('update_auto', True) is False:
        return False
    last = stored.get('update_checked')
    return not isinstance(last, (int, float)) or (now or time.time()) - last >= CHECK_INTERVAL
