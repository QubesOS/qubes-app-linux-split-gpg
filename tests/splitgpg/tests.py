# -*- coding: utf-8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2016 Marek Marczykowski-Górecki
#                               <marmarek@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
#
import unittest

import qubes.tests.extra


class SplitGPGBase(qubes.tests.extra.ExtraTestCase):
    def setUp(self):
        super(SplitGPGBase, self).setUp()
        self.enable_network()
        self.backend, self.frontend = self.create_vms(["backend", "frontend"])

        self.backend.start()
        if self.backend.run('ls /etc/qubes-rpc/qubes.Gpg', wait=True) != 0:
            self.skipTest('gpg-split not installed')
        # Whonix desynchronize time on purpose, so make sure the key is
        # generated in the past even when the frontend have clock few minutes
        #  into the future - otherwise new key may look as
        # generated in the future and be considered not yet valid
        if 'whonix' in self.template:
            self.backend.run("date -s -10min", user="root", wait=True)
        p = self.backend.run('mkdir -p -m 0700 .gnupg; gpg2 --gen-key --batch',
            passio_popen=True,
            passio_stderr=True)
        p.communicate('''
Key-Type: RSA
Key-Length: 1024
Key-Usage: sign encrypt
Name-Real: Qubes test
Name-Email: user@localhost
Expire-Date: 0
%no-protection
%commit
        '''.encode())
        if p.returncode == 127:
            self.skipTest('gpg2 not installed')
        elif p.returncode != 0:
            self.fail('key generation failed')
        if 'whonix' in self.template:
            self.backend.run("date -s +10min", user="root", wait=True)

        # fake confirmation
        self.backend.run(
            'touch /var/run/qubes-gpg-split/stat.{}'.format(
                self.frontend.name), wait=True)

        self.frontend.start()
        p = self.frontend.run('tee /rw/config/gpg-split-domain',
            passio_popen=True, user='root')
        p.communicate(self.backend.name.encode())

        self.qrexec_policy('qubes.Gpg', self.frontend.name, self.backend.name)
        self.qrexec_policy('qubes.GpgImportKey', self.frontend.name,
            self.backend.name)



class TC_00_Direct(SplitGPGBase):
    def test_000_version(self):
        cmd = 'qubes-gpg-client-wrapper --version'
        p = self.frontend.run(cmd, wait=True)
        self.assertEquals(p, 0, '{} failed'.format(cmd))

    def test_010_list_keys(self):
        cmd = 'qubes-gpg-client-wrapper --list-keys'
        p = self.frontend.run(cmd, passio_popen=True)
        (keys, _) = p.communicate()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertIn("Qubes test", keys.decode())

    def test_020_export_secret_key_deny(self):
        # TODO check if backend really deny such operation, here it is denied
        # by the frontend
        cmd = 'qubes-gpg-client-wrapper -a --export-secret-keys user@localhost'
        p = self.frontend.run(cmd, passio_popen=True)
        keys, _ = p.communicate()
        self.assertNotEquals(p.returncode, 0,
            '{} succeeded unexpectedly'.format(cmd))
        self.assertEquals(keys.decode(), '')

    def test_030_sign_verify(self):
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign'
        p = self.frontend.run(cmd, passio_popen=True)
        (signature, _) = p.communicate(msg.encode())
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertNotEquals('', signature.decode())

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (decoded_msg, verification_result) = p.communicate(signature)
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

        # verify in frontend directly
        cmd = 'gpg2 -a --export user@localhost'
        p = self.backend.run(cmd, passio_popen=True, passio_stderr=True)
        (pubkey, stderr) = p.communicate()
        self.assertEquals(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr.decode()))
        cmd = 'gpg2 --import'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(pubkey)
        self.assertEquals(p.returncode, 0,
            '{} failed: {}{}'.format(cmd, stdout.decode(), stderr.decode()))
        cmd = "gpg2"
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate(signature)
        self.assertEquals(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result.decode()))
        self.assertEquals(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    def test_031_sign_verify_detached(self):
        msg = "Test message"
        self.frontend.run('echo "{}" > message'.format(msg), wait=True)
        cmd = 'qubes-gpg-client-wrapper -a -b --sign message > signature.asc'
        p = self.frontend.run(cmd, wait=True)
        self.assertEquals(p, 0, '{} failed'.format(cmd))

        # verify through gpg-split
        cmd = 'qubes-gpg-client-wrapper --verify signature.asc message'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg.decode(), '')
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

        # break the message and check again
        self.frontend.run('echo "{}" >> message'.format(msg), wait=True)
        cmd = 'qubes-gpg-client-wrapper --verify signature.asc message'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertNotEquals(p.returncode, 0,
            '{} unexpecedly succeeded'.format(cmd))
        self.assertEquals(decoded_msg.decode(), '')
        self.assertIn('\ngpg: BAD signature from', verification_result.decode())

    def test_040_import(self):
        # see comment in setUp()
        if 'whonix' in self.template:
            self.frontend.run("date -s -10min", user="root", wait=True)
        p = self.frontend.run('mkdir -p -m 0700 .gnupg; gpg2 --gen-key --batch',
                passio_popen=True)
        p.communicate('''
Key-Type: RSA
Key-Length: 1024
Key-Usage: sign encrypt
Name-Real: Qubes test2
Name-Email: user2@localhost
Expire-Date: 0
%no-protection
%commit
        '''.encode())
        assert p.returncode == 0, 'key generation failed'
        # see comment in setUp()
        if 'whonix' in self.template:
            self.frontend.run("date -s +10min", user="root", wait=True)

        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertNotIn('user2@localhost', key_list.decode())
        p = self.frontend.run('gpg2 -a --export user2@localhost | '
            'QUBES_GPG_DOMAIN={} qubes-gpg-import-key'.format(self.backend.name),
            passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        self.assertEqual(p.returncode, 0, "Failed to import key: " +
                                          stderr.decode())
        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertIn('user2@localhost', key_list.decode())

    def test_041_import_via_wrapper(self):
        # see comment in setUp()
        if 'whonix' in self.template:
            self.frontend.run("date -s -10min", user="root", wait=True)
        p = self.frontend.run('mkdir -p -m 0700 .gnupg; gpg2 --gen-key --batch',
                passio_popen=True)
        p.communicate('''
Key-Type: RSA
Key-Length: 1024
Key-Usage: sign encrypt
Name-Real: Qubes test2
Name-Email: user2@localhost
Expire-Date: 0
%no-protection
%commit
        '''.encode())
        assert p.returncode == 0, 'key generation failed'
        # see comment in setUp()
        if 'whonix' in self.template:
            self.frontend.run("date -s +10min", user="root", wait=True)

        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertNotIn('user2@localhost', key_list.decode())
        p = self.frontend.run('gpg2 -a --export user2@localhost | '
            'QUBES_GPG_DOMAIN={} qubes-gpg-client-wrapper --import'.format(
                self.backend.name),
            passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        self.assertEqual(p.returncode, 0, "Failed to import key: " +
                                          stderr.decode())
        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertIn('user2@localhost', key_list.decode())


    def test_050_sign_verify_files(self):
        """Test for --output option"""
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign --output /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True)
        p.communicate(msg.encode())
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    def test_060_output_and_status_fd(self):
        """Regression test for #2057"""
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign --status-fd 1 --output ' \
              '/tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(msg.encode())
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertTrue(all(x.startswith('[GNUPG:]') for x in
            stdout.decode().splitlines()), "Non-status output on stdout")

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    def test_070_log_file_to_logger_fd(self):
        """Regression test for #3989"""
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign --log-file /tmp/gpg.log ' \
              '--verbose --output /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(msg.encode())
        self.assertEquals(p.returncode, 0, '{} failed: {}'.format(cmd,
            stderr.decode()))
        self.assertTrue(all(x.startswith('[GNUPG:]') for x in
            stdout.decode().splitlines()), "Non-status output on stdout")
        p = self.frontend.run('cat /tmp/gpg.log',
            passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        self.assertIn('signature from', stdout.decode())

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    # TODO:
    #  - encrypt/decrypt
    #  - large file (bigger than pipe/qrexec buffers)


class TC_10_Thunderbird(SplitGPGBase):

    scriptpath = '/usr/lib/qubes-gpg-split/test_thunderbird.py'

    def setUp(self):
        if self.template.startswith('whonix-gw'):
            self.skipTest('whonix-gw template not supported by this test')
        super(TC_10_Thunderbird, self).setUp()
        self.frontend.run_service('qubes.WaitForSession', wait=True,
            input='user')
        if self.frontend.run('which thunderbird', wait=True) == 0:
            self.tb_name = 'thunderbird'
        elif self.frontend.run('which icedove', wait=True) == 0:
            self.tb_name = 'icedove'
        else:
            self.skipTest('Thunderbird not installed')
        # use dogtail 0.9.10 directly from git, until 0.9.10 gets packaged in
        # relevant distros; 0.9.9 have problems with handling unicode
        p = self.frontend.run(
                'git clone -n https://gitlab.com/dogtail/dogtail && '
                'cd dogtail && '
                'git checkout 4d7923dcda92c2c44309d2a56b0bb616a1855155',
                passio_popen=True, passio_stderr=True)
        stdout, stderr = p.communicate()
        if p.returncode:
            self.skipTest(
                'dogtail installation failed: {}{}'.format(stdout, stderr))

        # fake confirmation again, in case dogtail installation took more
        # time (on slow network)
        self.backend.run(
            'touch /var/run/qubes-gpg-split/stat.{}'.format(
                self.frontend.name), wait=True)

        # if self.frontend.run(
        #         'python -c \'import dogtail,sys;'
        #         'sys.exit(dogtail.__version__ < "0.9.0")\'', wait=True) \
        #         != 0:
        #     self.skipTest('dogtail >= 0.9.0 testing framework not installed')

        # enigmail checks for ~/.gnupg dir...
        self.frontend.run('mkdir -p .gnupg', wait=True)

        p = self.frontend.run('gsettings set org.gnome.desktop.interface '
                              'toolkit-accessibility true', wait=True)
        assert p == 0, 'Failed to enable accessibility toolkit'
        if self.frontend.run(
                'ls {}'.format(self.scriptpath), wait=True):
            self.skipTest('qubes-gpg-split-tests package not installed')

        # run as root to not deal with /var/mail permission issues
        self.frontend.run(
            'touch /var/mail/user; chown user /var/mail/user', user='root',
            wait=True)
        self.smtp_server = self.frontend.run(
            'python3 /usr/lib/qubes-gpg-split/test_smtpd.py',
            user='root', passio_popen=True)

        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} setup 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        assert p.returncode == 0, 'Thunderbird setup failed: {}'.format(
            stdout.decode('ascii', 'ignore'))

        # fake confirmation again, to give more time for the actual test
        self.backend.run(
            'touch /var/run/qubes-gpg-split/stat.{}'.format(
                self.frontend.name), wait=True)

    def tearDown(self):
        self.smtp_server.terminate()
        del self.smtp_server
        super(TC_10_Thunderbird, self).tearDown()

    def test_000_send_receive_default(self):
        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} send_receive '
            '--encrypted --signed 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    def test_010_send_receive_inline_signed_only(self):
        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} '
            'send_receive '
            '--encrypted --signed --inline 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    def test_020_send_receive_inline_with_attachment(self):
        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} send_receive '
            '--encrypted --signed --inline --with-attachment 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))


class TC_20_Evolution(SplitGPGBase):

    scriptpath = '/usr/lib/qubes-gpg-split/test_evolution.py'

    def setUp(self):
        if self.template.startswith('whonix-gw'):
            self.skipTest('whonix-gw template not supported by this test')
        super(TC_20_Evolution, self).setUp()
        self.frontend.run_service('qubes.WaitForSession', wait=True,
            input='user')
        if self.frontend.run('which evolution', wait=True) != 0:
            self.skipTest('Evolution not installed')
        # use dogtail 0.9.10 directly from git, until 0.9.10 gets packaged in
        # relevant distros; 0.9.9 have problems with handling unicode
        p = self.frontend.run(
                'git clone -n https://gitlab.com/dogtail/dogtail && '
                'cd dogtail && '
                'git checkout 4d7923dcda92c2c44309d2a56b0bb616a1855155',
                passio_popen=True, passio_stderr=True)
        stdout, stderr = p.communicate()
        if p.returncode:
            self.skipTest(
                'dogtail installation failed: {}{}'.format(stdout, stderr))

        # if self.frontend.run(
        #         'python -c \'import dogtail,sys;'
        #         'sys.exit(dogtail.__version__ < "0.9.0")\'', wait=True) \
        #         != 0:
        #     self.skipTest('dogtail >= 0.9.0 testing framework not installed')

        # enigmail checks for ~/.gnupg dir...
        self.frontend.run('mkdir -p .gnupg', wait=True)

        p = self.frontend.run('gsettings set org.gnome.desktop.interface '
                              'toolkit-accessibility true', wait=True)
        assert p == 0, 'Failed to enable accessibility toolkit'
        if self.frontend.run(
                'ls {}'.format(self.scriptpath), wait=True):
            self.skipTest('qubes-gpg-split-tests package not installed')

        # run as root to not deal with /var/mail permission issues
        self.frontend.run(
            'touch /var/mail/user; chown user /var/mail/user', user='root',
            wait=True)
        self.smtp_server = self.frontend.run(
            'python3 /usr/lib/qubes-gpg-split/test_smtpd.py',
            user='root', passio_popen=True)

        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail python3 {} setup 2>&1'.format(
                self.scriptpath),
            passio_popen=True)
        (stdout, _) = p.communicate()
        assert p.returncode == 0, 'Evolution setup failed: {}'.format(
            stdout.decode('ascii', 'ignore'))

    def tearDown(self):
        self.smtp_server.terminate()
        del self.smtp_server
        super(TC_20_Evolution, self).tearDown()

    def test_000_send_receive_signed_encrypted(self):
        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail python3 {} send_receive '
            '--encrypted --signed 2>&1'.format(
                self.scriptpath),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Evolution send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    def test_010_send_receive_signed_only(self):
        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail python3 {} send_receive '
            '--encrypted --signed 2>&1'.format(
                self.scriptpath),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Evolution send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    @unittest.skip('handling attachments not done')
    def test_020_send_receive_with_attachment(self):
        p = self.frontend.run(
            'PYTHONPATH=$HOME/dogtail python3 {} send_receive '
            '--encrypted --signed --with-attachment 2>&1'.format(
                self.scriptpath),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Evolution send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

def list_tests():
    return (
        TC_00_Direct,
        TC_10_Thunderbird,
        TC_20_Evolution
    )
