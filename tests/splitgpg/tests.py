#!/usr/bin/python
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

import qubes.tests.extra


class SplitGPGBase(qubes.tests.extra.ExtraTestCase):
    def setUp(self):
        super(SplitGPGBase, self).setUp()
        self.enable_network()
        vms = self.create_vms(["backend", "frontend"])
        self.backend = vms[0]
        self.frontend = vms[1]

        self.backend.start()
        if self.backend.run('ls /etc/qubes-rpc/qubes.Gpg', wait=True) != 0:
            self.skipTest('gpg-split not installed')
        p = self.backend.run('gpg --gen-key --batch', passio_popen=True)
        p.stdin.write('''
Key-Type: RSA
Key-Length: 1024
Key-Usage: sign encrypt
Name-Real: Qubes test
Name-Email: user@localhost
Expire-Date: 0
%commit
        ''')
        p.stdin.close()
        # discard stdout
        p.stdout.read()
        p.wait()
        assert p.returncode == 0, 'key generation failed'

        # fake confirmation
        self.backend.run(
            'touch /var/run/qubes-gpg-split/stat.{}'.format(self.frontend.name))

        self.frontend.start()
        p = self.frontend.run('tee /rw/config/gpg-split-domain',
            passio_popen=True, user='root')
        p.stdin.write(self.backend.name)
        p.stdin.close()
        p.wait()

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
        keys = p.stdout.read()
        p.wait()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertIn("Qubes test", keys)

    def test_020_export_secret_key_deny(self):
        # TODO check if backend really deny such operation, here it is denied
        # by the frontend
        cmd = 'qubes-gpg-client-wrapper -a --export-secret-keys user@localhost'
        p = self.frontend.run(cmd, passio_popen=True)
        keys = p.stdout.read()
        p.wait()
        self.assertNotEquals(p.returncode, 0,
            '{} succeeded unexpectedly'.format(cmd))
        self.assertEquals(keys, '')

    def test_030_sign_verify(self):
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign'
        p = self.frontend.run(cmd, passio_popen=True)
        p.stdin.write(msg)
        p.stdin.close()
        signature = p.stdout.read()
        p.wait()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertNotEquals('', signature)

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        p.stdin.write(signature)
        p.stdin.close()
        decoded_msg = p.stdout.read()
        verification_result = p.stderr.read()
        p.wait()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg, msg)
        self.assertIn('\ngpg: Good signature from', verification_result)

        # verify in frontend directly
        cmd = 'gpg -a --export user@localhost'
        p = self.backend.run(cmd, passio_popen=True, passio_stderr=True)
        (pubkey, stderr) = p.communicate()
        self.assertEquals(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr))
        cmd = 'gpg --import'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(pubkey)
        self.assertEquals(p.returncode, 0,
            '{} failed: {}{}'.format(cmd, stdout, stderr))
        cmd = "gpg"
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        p.stdin.write(signature)
        p.stdin.close()
        decoded_msg = p.stdout.read()
        verification_result = p.stderr.read()
        p.wait()
        self.assertEquals(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result))
        self.assertEquals(decoded_msg, msg)
        self.assertIn('\ngpg: Good signature from', verification_result)

    def test_031_sign_verify_detached(self):
        msg = "Test message"
        self.frontend.run('echo "{}" > message'.format(msg), wait=True)
        cmd = 'qubes-gpg-client-wrapper -a -b --sign message > signature.asc'
        p = self.frontend.run(cmd, wait=True)
        self.assertEquals(p, 0, '{} failed'.format(cmd))

        # verify through gpg-split
        cmd = 'qubes-gpg-client-wrapper --verify signature.asc message'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg = p.stdout.read()
        verification_result = p.stderr.read()
        p.wait()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg, '')
        self.assertIn('\ngpg: Good signature from', verification_result)

        # break the message and check again
        self.frontend.run('echo "{}" >> message'.format(msg), wait=True)
        cmd = 'qubes-gpg-client-wrapper --verify signature.asc message'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg = p.stdout.read()
        verification_result = p.stderr.read()
        p.wait()
        self.assertNotEquals(p.returncode, 0,
            '{} unexpecedly succeeded'.format(cmd))
        self.assertEquals(decoded_msg, '')
        self.assertIn('\ngpg: BAD signature from', verification_result)

    def test_040_import(self):
        p = self.frontend.run('gpg --gen-key --batch', passio_popen=True)
        p.stdin.write('''
Key-Type: RSA
Key-Length: 1024
Key-Usage: sign encrypt
Name-Real: Qubes test2
Name-Email: user2@localhost
Expire-Date: 0
%commit
        ''')
        p.stdin.close()
        # discard stdout
        p.stdout.read()
        p.wait()
        assert p.returncode == 0, 'key generation failed'

        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertNotIn('user2@localhost', key_list)
        p = self.frontend.run('gpg -a --export user2@localhost | '
            'QUBES_GPG_DOMAIN={} qubes-gpg-import-key'.format(self.backend.name),
            passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        self.assertEqual(p.returncode, 0, "Failed to import key: " + stderr)
        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertIn('user2@localhost', key_list)

    def test_041_import_via_wrapper(self):
        p = self.frontend.run('gpg --gen-key --batch', passio_popen=True)
        p.stdin.write('''
Key-Type: RSA
Key-Length: 1024
Key-Usage: sign encrypt
Name-Real: Qubes test2
Name-Email: user2@localhost
Expire-Date: 0
%commit
        ''')
        p.stdin.close()
        # discard stdout
        p.stdout.read()
        p.wait()
        assert p.returncode == 0, 'key generation failed'

        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertNotIn('user2@localhost', key_list)
        p = self.frontend.run('gpg -a --export user2@localhost | '
            'QUBES_GPG_DOMAIN={} qubes-gpg-client-wrapper --import'.format(
                self.backend.name),
            passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        self.assertEqual(p.returncode, 0, "Failed to import key: " + stderr)
        p = self.frontend.run('qubes-gpg-client-wrapper --list-keys',
            passio_popen=True)
        (key_list, _) = p.communicate()
        self.assertIn('user2@localhost', key_list)


    def test_050_sign_verify_files(self):
        """Test for --output option"""
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign --output /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True)
        p.stdin.write(msg)
        p.stdin.close()
        p.wait()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg, msg)
        self.assertIn('\ngpg: Good signature from', verification_result)

    def test_060_output_and_status_fd(self):
        """Regression test for #2057"""
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign --status-fd 1 --output ' \
              '/tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(msg)
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertTrue(all(x.startswith('[GNUPG:]') for x in
            stdout.splitlines()), "Non-status output on stdout")

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEquals(p.returncode, 0, '{} failed'.format(cmd))
        self.assertEquals(decoded_msg, msg)
        self.assertIn('\ngpg: Good signature from', verification_result)

    # TODO:
    #  - encrypt/decrypt
    #  - large file (bigger than pipe/qrexec buffers)


class TC_10_Thunderbird(SplitGPGBase):

    scriptpath = '/usr/lib/qubes-gpg-split/test_thunderbird.py'

    def setUp(self):
        super(TC_10_Thunderbird, self).setUp()
        if self.frontend.run('which thunderbird', wait=True) == 0:
            self.tb_name = 'thunderbird'
        elif self.frontend.run('which icedove', wait=True) == 0:
            self.tb_name = 'icedove'
        else:
            self.skipTest('Thunderbird not installed')
        # if self.frontend.run(
        #         'python -c \'import dogtail,sys;'
        #         'sys.exit(dogtail.__version__ < "0.9.0")\'', wait=True) \
        #         != 0:
        #     self.skipTest('dogtail >= 0.9.0 testing framework not installed')

        p = self.frontend.run('gsettings set org.gnome.desktop.interface '
                              'toolkit-accessibility true', wait=True)
        assert p == 0, 'Failed to enable accessibility toolkit'
        if self.frontend.run(
                'ls {}'.format(self.scriptpath), wait=True):
            self.skipTest('qubes-gpg-split-tests package not installed')

        # run as root to not deal with /var/mail permission issues
        self.frontend.run(
            'touch /var/mail/user; chown user /var/mail/user', user='root')
        self.frontend.run('python /usr/lib/qubes-gpg-split/test_smtpd.py',
            user='root')

        p = self.frontend.run(
            'PYTHONIOENCODING=utf-8 python {} --tbname={} setup 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        assert p.returncode == 0, 'Thunderbird setup failed: {}'.format(stdout)

    def test_000_send_receive_default(self):
        p = self.frontend.run(
            'PYTHONIOENCODING=utf-8 python {} --tbname={} send_receive '
            '--encrypted --signed 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(stdout))

    def test_010_send_receive_inline_signed_only(self):
        p = self.frontend.run(
            'PYTHONIOENCODING=utf-8 python {} --tbname={} send_receive '
            '--encrypted --signed --inline 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(stdout))

    def test_020_send_receive_inline_with_attachment(self):
        p = self.frontend.run(
            'PYTHONIOENCODING=utf-8 python {} --tbname={} send_receive '
            '--encrypted --signed --inline --with-attachment 2>&1'.format(
                self.scriptpath, self.tb_name),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEquals(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(stdout))


def list_tests():
    return (
        TC_00_Direct,
        TC_10_Thunderbird
    )
