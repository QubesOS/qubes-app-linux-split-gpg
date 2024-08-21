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
Key-Usage: sign
Subkey-Type: RSA
Subkey-Length: 1024
Subkey-Usage: encrypt
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

        self.fake_confirmation()

        self.frontend.start()
        p = self.frontend.run('tee /rw/config/gpg-split-domain',
            passio_popen=True, user='root')
        p.communicate(self.backend.name.encode())

        self.qrexec_policy('qubes.Gpg', self.frontend.name, self.backend.name)
        self.qrexec_policy('qubes.GpgImportKey', self.frontend.name,
            self.backend.name)

    def fake_confirmation(self):
        # fake confirmation
        self.backend.run(
            'touch /var/run/qubes-gpg-split/stat.{}'.format(
                self.frontend.name), wait=True)


class TC_00_Direct(SplitGPGBase):
    def test_000_version(self):
        cmd = 'qubes-gpg-client-wrapper --version'
        p = self.frontend.run(cmd, wait=True)
        self.assertEqual(p, 0, '{} failed'.format(cmd))

    def test_010_list_keys(self):
        cmd = 'qubes-gpg-client-wrapper --list-keys'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (keys, stderr) = p.communicate()
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr.decode()))
        self.assertIn("Qubes test", keys.decode())

    def test_020_export_secret_key_deny(self):
        # TODO check if backend really deny such operation, here it is denied
        # by the frontend
        cmd = 'qubes-gpg-client-wrapper -a --export-secret-keys user@localhost'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        keys, stderr = p.communicate()
        self.assertNotEqual(p.returncode, 0,
            '{} succeeded unexpectedly: {}'.format(cmd, stderr.decode()))
        self.assertEqual(keys.decode(), '')

    def test_030_sign_verify(self):
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (signature, stderr) = p.communicate(msg.encode())
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr.decode()))
        self.assertNotEqual('', signature.decode())

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (decoded_msg, verification_result) = p.communicate(signature)
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result.decode()))
        self.assertEqual(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

        # verify in frontend directly
        cmd = 'gpg2 -a --export user@localhost'
        p = self.backend.run(cmd, passio_popen=True, passio_stderr=True)
        (pubkey, stderr) = p.communicate()
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr.decode()))
        cmd = 'gpg2 --import'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(pubkey)
        self.assertEqual(p.returncode, 0,
            '{} failed: {}{}'.format(cmd, stdout.decode(), stderr.decode()))
        cmd = "gpg2"
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate(signature)
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result.decode()))
        self.assertEqual(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    def test_031_sign_verify_detached(self):
        msg = "Test message"
        self.frontend.run('echo "{}" > message'.format(msg), wait=True)
        cmd = 'qubes-gpg-client-wrapper -a -b --sign message > signature.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        stdout, stderr = p.communicate()
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr.decode()))

        # verify through gpg-split
        cmd = 'qubes-gpg-client-wrapper --verify signature.asc message'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result.decode()))
        self.assertEqual(decoded_msg.decode(), '')
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

        # break the message and check again
        self.frontend.run('echo "{}" >> message'.format(msg), wait=True)
        cmd = 'qubes-gpg-client-wrapper --verify signature.asc message'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertNotEqual(p.returncode, 0,
            '{} unexpecedly succeeded: {}'.format(cmd, verification_result.decode()))
        self.assertEqual(decoded_msg.decode(), '')
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
Key-Usage: sign
Subkey-Type: RSA
Subkey-Length: 1024
Subkey-Usage: encrypt
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
                passio_popen=True, passio_stderr=True)
        stdout, stderr = p.communicate('''
Key-Type: RSA
Key-Length: 1024
Key-Usage: sign
Subkey-Type: RSA
Subkey-Length: 1024
Subkey-Usage: encrypt
Name-Real: Qubes test2
Name-Email: user2@localhost
Expire-Date: 0
%no-protection
%commit
        '''.encode())
        assert p.returncode == 0, 'key generation failed: {}'.format(
            stderr.decode())
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
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        stdout, stderr = p.communicate(msg.encode())
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr.decode()))

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result.decode()))
        self.assertEqual(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    def test_060_output_and_status_fd(self):
        """Regression test for #2057"""
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign --status-fd 1 --output ' \
              '/tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(msg.encode())
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, stderr.decode()))
        self.assertTrue(all(x.startswith('[GNUPG:]') for x in
            stdout.decode().splitlines()), "Non-status output on stdout")

        # verify first through gpg-split
        cmd = 'qubes-gpg-client-wrapper /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        decoded_msg, verification_result = p.communicate()
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result.decode()))
        self.assertEqual(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    def test_070_log_file_to_logger_fd(self):
        """Regression test for #3989"""
        msg = "Test message"
        cmd = 'qubes-gpg-client-wrapper -a --sign --log-file /tmp/gpg.log ' \
              '--verbose --output /tmp/signed.asc'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate(msg.encode())
        self.assertEqual(p.returncode, 0, '{} failed: {}'.format(cmd,
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
        self.assertEqual(p.returncode, 0,
            '{} failed: {}'.format(cmd, verification_result.decode()))
        self.assertEqual(decoded_msg.decode(), msg)
        self.assertIn('\ngpg: Good signature from', verification_result.decode())

    def _check_if_options_takes_argument(self, prog, option, message_fmts):
        """Check whether an option expect an argument or not.
        The *prog* will be called with *option* and --garbage-1 --garbage-2.
        Based on which one is rejected, it will deduce whether the option
        requires an argument or not.

        :param prog: program to test (gpg2, qubes-gpg-client)
        :param option: option to test
        :param message_fmt: error message format, about rejected option
        """

        # check if option requires an argument by seeing if --garbage-1 was
        # interpreted as another option, or an argument
        cmd = '{} {} --garbage-1 --garbage-2'.format(prog, option)
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        stderr = stderr.decode()
        self.assertNotEqual(p.returncode, 0,
            cmd + ' should have failed: ' + stderr)
        if option == '--list-options' and 'qubes' in prog:
             self.assertEqual(stderr,
                 "qubes-gpg-client: Unknown list option --garbage-1\n")
             return True
        if option == '--verify-options' and 'qubes' in prog:
             self.assertEqual(stderr,
                 "qubes-gpg-client: Unknown verify option --garbage-1\n")
             return True
        if option == '--export-options' and 'qubes' in prog:
             self.assertEqual(stderr,
                 "qubes-gpg-client: Unknown export option --garbage-1\n")
             return True
        for message_fmt in message_fmts:
            if message_fmt.format('--garbage-1') in stderr:
                return False
            if message_fmt.format('--garbage-2') in stderr:
                return True
            if message_fmt.format(option) in stderr:
                return None
        if 'invalid argument for option "{}"'.format(option) in stderr:
            return True
        if 'Invalid fd argument' in stderr:
            return True
        self.fail(
            '{} {} have not complained about --garbage options: {}'.format(
                'qubes-gpg-client' if 'qubes' in prog else 'gpg2',
                option, stderr))

    def test_080_option_parser(self):
        """Check if split-gpg agrees with gpg about options parsing"""
        cmd = 'gpg --dump-options'
        p = self.frontend.run(cmd, passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        self.assertEqual(p.returncode, 0, '{} failed: {}'.format(cmd,
            stderr.decode()))
        all_options = stdout.decode().splitlines()
        noarg_options = []
        for opt in all_options:
            if opt in ('--output', '--logger-fd', '--version'):
                # those options are problematic for testing (different error
                # messages, messes with logging) and are checked manually
                continue
            splitgpg_needs_arg = self._check_if_options_takes_argument(
                'QUBES_GPG_DOMAIN={} qubes-gpg-client'.format(self.backend.name),
                opt, ['unrecognized option \'{}\'',
                      'option \'{}\' is ambiguous',
                      'Forbidden option: {}'])
            if splitgpg_needs_arg is None:
                # option rejected
                continue
            gpg_needs_arg = self._check_if_options_takes_argument(
                'gpg2', opt, ['invalid option "{}"'])
            self.assertEqual(gpg_needs_arg, splitgpg_needs_arg,
                'gpg and splitgpg disagrees on {} option: {}, {}'.format(
                    opt, gpg_needs_arg, splitgpg_needs_arg))
            if not gpg_needs_arg:
                noarg_options.append(opt)
        # TODO: Test if gpg agrees with split-gpg, whether positional
        #  argument(s) are a path or user id. Somehow...

    def test_081_subpacket_options(self):
        """Check if split-gpg agrees with gpg about subpacket options parsing"""
        p = self.frontend.run('QUBES_GPG_DOMAIN=bogus qubes-gpg-client '
                              '--list-options show-sig-subpackets=1+1',
                              passio_popen=True, passio_stderr=True)
        (stdout, stderr) = p.communicate()
        self.assertEqual(stdout, b'', 'nothing should appear on stdout')
        self.assertEqual(stderr,
                         b'qubes-gpg-client: Invalid character + following '
                         b'subpacket number\n',
                         'bad subpacket number not rejected properly')
        assert p.wait() == 1, 'wrong exit code'

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

        p = self.frontend.run('gsettings set org.gnome.desktop.interface '
                              'toolkit-accessibility true', wait=True)
        assert p == 0, 'Failed to enable accessibility toolkit'
        if self.frontend.run(
                'ls {}'.format(self.scriptpath), wait=True):
            self.skipTest('qubes-gpg-split-tests package not installed')

        # run as root to not deal with /var/mail permission issues
        self.frontend.run(
            'mkdir -p Mail/new Mail/cur Mail/tmp',
            wait=True)

        # SMTP configuration
        self.smtp_server = self.frontend.run(
            'aiosmtpd -n -c aiosmtpd.handlers.Mailbox /home/user/Mail',
            passio_popen=True)

        # IMAP configuration
        self.imap_pw = "pass"
        self.frontend.run(
            'echo "mail_location=maildir:~/Mail" |\
                sudo tee /etc/dovecot/conf.d/100-mail.conf', wait=True)
        self.frontend.run('sudo systemctl restart dovecot', wait=True)
        self.frontend.run( # set a user password because IMAP needs one for auth
            'sudo usermod -p `echo "{}" | openssl passwd --stdin` user'\
                .format(self.imap_pw),
            wait=True)

        self.setup_tb_profile(setup_openpgp=True)

        p = self.frontend.run(
            'LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} --profile {} --imap_pw {} setup 2>&1'.format(
                self.scriptpath, self.tb_name, self.profile_dir, self.imap_pw),
            passio_popen=True)
        (stdout, _) = p.communicate()
        assert p.returncode == 0, 'Thunderbird setup failed: {}'.format(
            stdout.decode('ascii', 'ignore'))

        # fake confirmation again, to give more time for the actual test
        self.fake_confirmation()

    def tearDown(self):
        self.smtp_server.terminate()
        del self.smtp_server
        super(TC_10_Thunderbird, self).tearDown()

    def get_key_fpr(self):
        cmd = '/usr/bin/qubes-gpg-client-wrapper -K --with-colons'
        p = self.frontend.run(cmd, passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0, 'Failed to determin key id')
        keyid = stdout.decode('utf-8').split('\n')[1]
        keyid = keyid.split(':')[9]
        keyid = keyid[-16:]
        return keyid

    def setup_tb_profile(self, setup_openpgp):
        """SplitGPG Thunderbird Test Account Configuration

        Originally generated by running thunderbird for the first time
        and taking from ~/.thunderbird/<PROFILE>.default/prefs.js all
        the relevant settings. Then adding the opengpg settings.
        """

        profile_base = """
user_pref("mail.accountmanager.accounts", "account1");
user_pref("mail.accountmanager.defaultaccount", "account1");
user_pref("mail.account.account1.identities", "id1");
user_pref("mail.account.account1.server", "server1");
user_pref("mail.identity.id1.fullName", "user");
user_pref("mail.identity.id1.useremail", "user@localhost");
user_pref("mail.identity.id1.smtpServer", "smtp1");
user_pref("mail.identity.id1.compose_html", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false); // avoid message popups
user_pref("app.donation.eoy.version.viewed", 100); // avoid message popups
"""
        imap_server = """
user_pref("mail.server.server1.userName", "user");
user_pref("mail.server.server1.hostname", "localhost");
user_pref("mail.server.server1.login_at_startup", true);
user_pref("mail.server.server1.name", "user@localhost");
user_pref("mail.server.server1.type", "imap");
user_pref("mail.server.server1.port", 143);
"""
        smtp_server = """
user_pref("mail.smtpservers", "smtp1");
user_pref("mail.smtp.defaultserver", "smtp1");
user_pref("mail.smtpserver.smtp1.username", "user");
user_pref("mail.smtpserver.smtp1.hostname", "localhost");
user_pref("mail.smtpserver.smtp1.port", 8025);
user_pref("mail.smtpserver.smtp1.authMethod", 3); // no auth
user_pref("mail.smtpserver.smtp1.try_ssl", 0);    // no encryption
"""
        open_pgp = """
user_pref("mail.openpgp.allow_external_gnupg", true);
user_pref("mail.openpgp.alternative_gpg_path", "/usr/bin/qubes-gpg-client-wrapper");
"""
        key_fingerprint = self.get_key_fpr()
        user_account_pgp = """
user_pref("mail.identity.id1.is_gnupg_key_id", true);
user_pref("mail.identity.id1.last_entered_external_gnupg_key_id", "{}");
user_pref("mail.identity.id1.openpgp_key_id", "{}");
user_pref("mail.identity.id1.sign_mail", false);
""".format(key_fingerprint, key_fingerprint)

        self.profile_dir = "$HOME/.thunderbird/qubes.default"
        user_js_path = self.profile_dir + "/user.js"

        user_js = profile_base + imap_server + smtp_server
        if setup_openpgp:
            user_js += open_pgp + user_account_pgp

        self.frontend.run('mkdir -p {}'.format(self.profile_dir),
                          user='user', wait=True)
        p = self.frontend.run('cat > ' + user_js_path,
                          user='user', passio_popen=True)
        (stdout, _) = p.communicate(user_js.encode())
        assert p.returncode == 0, 'Thunderbird profile configuration failed: {}'\
            .format(stdout.decode('ascii', 'ignore'))

    def test_000_send_receive_default(self):
        p = self.frontend.run(
            'LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} --profile {} --imap_pw {} send_receive '
            '--encrypted --signed 2>&1'.format(
                self.scriptpath, self.tb_name, self.profile_dir, self.imap_pw),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    def test_010_send_receive_inline_signed_only(self):
        p = self.frontend.run(
            'LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} --profile {} --imap_pw {} send_receive '
            '--encrypted --signed --inline 2>&1'.format(
                self.scriptpath, self.tb_name, self.profile_dir, self.imap_pw),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0,
            'Thunderbird send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    def test_020_send_receive_inline_with_attachment(self):
        p = self.frontend.run(
            'LC_ALL=C.UTF-8 '
            'python3 {} --tbname={} --profile {} --imap_pw {} send_receive '
            '--encrypted --signed --inline --with-attachment 2>&1'.format(
                self.scriptpath, self.tb_name, self.profile_dir, self.imap_pw),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0,
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

        p = self.frontend.run('gsettings set org.gnome.desktop.interface '
                              'toolkit-accessibility true', wait=True)
        assert p == 0, 'Failed to enable accessibility toolkit'
        if self.frontend.run(
                'ls {}'.format(self.scriptpath), wait=True):
            self.skipTest('qubes-gpg-split-tests package not installed')

        # run as root to not deal with /var/mail permission issues
        self.frontend.run(
            'mkdir -p Mail/new Mail/cur Mail/tmp',
            wait=True)
        self.smtp_server = self.frontend.run(
            'aiosmtpd -n -c aiosmtpd.handlers.Mailbox /home/user/Mail',
            passio_popen=True)

        p = self.frontend.run(
            'python3 {} setup 2>&1'.format(
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
            'python3 {} send_receive '
            '--encrypted --signed 2>&1'.format(
                self.scriptpath),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0,
            'Evolution send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    def test_010_send_receive_signed_only(self):
        p = self.frontend.run(
            'python3 {} send_receive '
            '--signed 2>&1'.format(
                self.scriptpath),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0,
            'Evolution send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

    @unittest.skip('handling attachments not done')
    def test_020_send_receive_with_attachment(self):
        p = self.frontend.run(
            'python3 {} send_receive '
            '--encrypted --signed --with-attachment 2>&1'.format(
                self.scriptpath),
            passio_popen=True)
        (stdout, _) = p.communicate()
        self.assertEqual(p.returncode, 0,
            'Evolution send/receive failed: {}'.format(
                stdout.decode('ascii', 'ignore')))

def list_tests():
    return (
        TC_00_Direct,
        TC_10_Thunderbird,
        TC_20_Evolution
    )
