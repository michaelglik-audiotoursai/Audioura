"""LOCAL-899: is_test honored for allow-listed proof users (TOUR_TEST_PROOF_USER_IDS). $0, no network."""
import os, sys, io, re, unittest, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tour_orchestrator_service as svc

ENVS = ('TOUR_TEST_MODE', 'TOUR_TEST_MODE_ALLOW_REQUEST', 'TOUR_TEST_PROOF_USER_IDS')


class ProofIsTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in ENVS}

    def tearDown(self):
        for k, v in self._saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def resolve(self, user, raw, **env):
        os.environ.update(env)
        c = svc.app.test_client()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # unsupported language -> 400 right after the is_test resolution/log line
            c.post('/generate-complete-tour', json={'location': 'X', 'user_id': user, 'is_test': raw, 'language': 'xx'})
        m = re.search(r'is_test: (\S+) \(raw=(.*?), server_mode=(\w+), allow_request=(\w+), proof_user=(\w+)\)', buf.getvalue())
        self.assertIsNotNone(m, buf.getvalue()[-500:])
        return m.group(1), m.groups()

    def test_listed_user_true(self):
        v, g = self.resolve('USER-1073427300', True, TOUR_TEST_PROOF_USER_IDS='USER-1073427300')
        self.assertEqual(v, 'True'); self.assertEqual(g[4], 'True')

    def test_listed_among_many(self):
        self.assertEqual(self.resolve('USER-2', True, TOUR_TEST_PROOF_USER_IDS='USER-1, USER-2')[0], 'True')

    def test_unlisted_user_false(self):
        v, g = self.resolve('USER-999', True, TOUR_TEST_PROOF_USER_IDS='USER-1073427300')
        self.assertEqual(v, 'None'); self.assertEqual(g[4], 'False')

    def test_env_unset(self):
        self.assertEqual(self.resolve('USER-1073427300', True)[0], 'None')

    def test_listed_false_stays_false(self):
        for raw in (False, None, 'false', '0'):
            self.assertEqual(self.resolve('USER-1', raw, TOUR_TEST_PROOF_USER_IDS='USER-1')[0], 'None', raw)

    def test_server_mode_unchanged(self):
        self.assertEqual(self.resolve('anyone', True, TOUR_TEST_MODE='true')[0], 'True')
        self.assertEqual(self.resolve('anyone', True, TOUR_TEST_MODE_ALLOW_REQUEST='true')[0], 'True')
        self.assertEqual(self.resolve('anyone', False, TOUR_TEST_MODE='true')[0], 'None')

    def test_empty_user_not_listed(self):
        self.assertFalse(svc._is_proof_test_user(''))
        self.assertFalse(svc._is_proof_test_user(None))


if __name__ == '__main__':
    unittest.main()
