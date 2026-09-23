import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from exile_worth import updater
from exile_worth.updater import UpdateError


def api_answer(tag='v0.2.0', installer='ExileWorth-Setup-0.2.0.exe', host='github.com', **extra):
    base = f'https://{host}/SylvainRiom/exile-worth/releases/download/{tag}/'
    assets = [{'name': installer, 'size': 3, 'browser_download_url': base + installer},
              {'name': installer + '.sha256', 'size': 90, 'browser_download_url': base + installer + '.sha256'}]
    return {'tag_name': tag, 'html_url': f'https://github.com/SylvainRiom/exile-worth/releases/tag/{tag}',
            'draft': False, 'prerelease': False, 'assets': assets} | extra


class Response(io.BytesIO):
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body) if length is None else length)}


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version('v1.2.10'), (1, 2, 10))
        self.assertEqual(updater.parse_version('0.1.0'), (0, 1, 0))
        for text in ('v1.2', '1.2.3-beta', 'latest', '', None):
            self.assertIsNone(updater.parse_version(text), text)

    def test_numeric_not_textual_order(self):
        self.assertIsNotNone(updater.newer_release('0.9.0', lambda: api_answer('v0.10.0', 'ExileWorth-Setup-0.10.0.exe')))

    def test_only_a_newer_version_is_offered(self):
        self.assertIsNotNone(updater.newer_release('0.1.0', lambda: api_answer()))
        self.assertIsNone(updater.newer_release('0.2.0', lambda: api_answer()))
        self.assertIsNone(updater.newer_release('0.3.0', lambda: api_answer()))

    def test_no_release_at_all_is_not_newer(self):
        self.assertIsNone(updater.newer_release('0.1.0', lambda: {}))

    def test_the_package_version_is_parseable(self):
        from exile_worth import __version__
        self.assertIsNotNone(updater.parse_version(__version__))


class ReleaseTests(unittest.TestCase):
    def test_complete_release(self):
        release = updater.release_from(api_answer())
        self.assertEqual((release.label, release.installer_name), ('0.2.0', 'ExileWorth-Setup-0.2.0.exe'))
        self.assertTrue(release.checksum_url.endswith('.sha256'))

    def test_without_checksum_or_installer_it_is_not_installable(self):
        answer = api_answer()
        answer['assets'] = answer['assets'][:1]
        self.assertIsNone(updater.release_from(answer))
        self.assertIsNone(updater.release_from(api_answer(installer='ExileWorth-Setup-0.1.9.exe')))

    def test_drafts_prereleases_and_bad_tags_are_ignored(self):
        self.assertIsNone(updater.release_from(api_answer(draft=True)))
        self.assertIsNone(updater.release_from(api_answer(prerelease=True)))
        self.assertIsNone(updater.release_from(api_answer(tag='nightly')))

    def test_an_asset_on_another_host_is_refused(self):
        self.assertIsNone(updater.release_from(api_answer(host='github.com.evil.example')))
        self.assertFalse(updater.permitted('https://github.com@evil.example/x.exe'))
        self.assertFalse(updater.permitted('http://github.com/x.exe'))

    def test_redirects_are_pinned(self):
        handler = updater.PinnedRedirects()
        with self.assertRaises(UpdateError) as caught:
            handler.redirect_request(None, None, 302, 'Found', {}, 'https://evil.example/x.exe')
        self.assertEqual(caught.exception.key, 'host')


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.release = updater.release_from(api_answer())
        self.body = b'installer bytes'

    def tearDown(self):
        self.temp.cleanup()

    def opener(self, checksum, body=None, length=None):
        def open_url(url, timeout):
            if url.endswith('.sha256'):
                return Response(checksum.encode())
            return Response(self.body if body is None else body, length)
        return open_url

    def test_verified_download(self):
        digest = hashlib.sha256(self.body).hexdigest()
        seen = []
        path = updater.download(self.release, self.directory, lambda done, total: seen.append((done, total)),
                                self.opener(f'{digest}  ExileWorth-Setup-0.2.0.exe\n'))
        self.assertEqual(path.read_bytes(), self.body)
        self.assertEqual(seen[-1], (len(self.body), len(self.body)))
        self.assertEqual([p.name for p in self.directory.iterdir()], ['ExileWorth-Setup-0.2.0.exe'])

    def test_a_mismatched_download_is_deleted(self):
        wrong = hashlib.sha256(b'other').hexdigest()
        with self.assertRaises(UpdateError) as caught:
            updater.download(self.release, self.directory, None, self.opener(f'{wrong}  ExileWorth-Setup-0.2.0.exe'))
        self.assertEqual(caught.exception.key, 'checksum')
        self.assertEqual(list(self.directory.iterdir()), [], 'Nothing is left to run')

    def test_a_checksum_for_another_file_is_refused(self):
        digest = hashlib.sha256(self.body).hexdigest()
        with self.assertRaises(UpdateError):
            updater.download(self.release, self.directory, None, self.opener(f'{digest}  other.exe'))

    def test_an_oversized_download_stops(self):
        original = updater.MAX_INSTALLER
        updater.MAX_INSTALLER = 4
        try:
            digest = hashlib.sha256(self.body).hexdigest()
            with self.assertRaises(UpdateError) as caught:
                updater.download(self.release, self.directory, None, self.opener(digest))
            self.assertEqual(caught.exception.key, 'size')
        finally:
            updater.MAX_INSTALLER = original
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_clean_removes_old_installers_only(self):
        (self.directory / 'ExileWorth-Setup-0.1.0.exe').write_bytes(b'x')
        (self.directory / 'keep.txt').write_text('x')
        updater.clean(self.directory)
        self.assertEqual([p.name for p in self.directory.iterdir()], ['keep.txt'])
        updater.clean(self.directory / 'missing')


class ScheduleTests(unittest.TestCase):
    def test_daily_and_switchable(self):
        self.assertTrue(updater.due({}))
        self.assertFalse(updater.due({'update_checked': 1000.0}, now=1000.0 + 3600))
        self.assertTrue(updater.due({'update_checked': 1000.0}, now=1000.0 + updater.CHECK_INTERVAL))
        self.assertFalse(updater.due({'update_auto': False}))

    def test_enabled_in_packaged_builds_only_unless_forced(self):
        self.assertFalse(updater.enabled({}))
        self.assertTrue(updater.enabled({'EXILE_UPDATE_CHECK': '1'}))
        self.assertFalse(updater.enabled({'EXILE_UPDATE_CHECK': '0'}))

    def test_installer_arguments_match_the_installer_script(self):
        command = updater.install_command(Path('setup.exe'), 'fr')
        self.assertIn('/RELAUNCH=1', command)
        self.assertIn('/LANG=fr', command)
        script = (Path(__file__).parent.parent / 'packaging' / 'installer.iss').read_text('utf-8')
        self.assertIn("{param:RELAUNCH|0}", script)
        self.assertIn('Name: "fr"', script)


if __name__ == '__main__':
    unittest.main()
