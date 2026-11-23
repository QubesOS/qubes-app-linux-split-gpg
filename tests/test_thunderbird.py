#!/usr/bin/python3
# vim: fileencoding=utf-8

#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2016 Marek Marczykowski-Górecki
#                                       <marmarek@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
import argparse

import dogtail
from dogtail import tree, rawinput
from dogtail.predicate import GenericPredicate
from dogtail.config import config
import contextlib
import subprocess
import os
import re
import time
import functools

dogtail_1x = dogtail.__version__.startswith(("0.", "1."))

subject = 'Test message {}'.format(os.getpid())

defaultCutoffCount = 10

if not dogtail_1x:
    config.action_delay = 1.0
    config.default_delay = 1.0
    config.search_cut_off_limit = defaultCutoffCount
else:
    config.actionDelay = 1.0
    config.defaultDelay = 1.0
    config.searchCutoffCount = defaultCutoffCount


class orPredicate(GenericPredicate):
    def __init__(self, *predicates):
        self.predicates = predicates
        super().__init__()
        if not dogtail_1x:
            # dogtail 2.x
            self.satisfied_by_node = self._genCompareFunc()
            self.description = ' or '.join(str(p.description) for p in self.predicates)
        else:
            self.satisfiedByNode = self._genCompareFunc()

    def _genCompareFunc(self):
        if dogtail_1x:
            funcs = [p.satisfiedByNode for p in self.predicates]
        else:
            funcs = [p.satisfied_by_node for p in self.predicates]

        def satisfiedByNode(node):
            return any(f(node) for f in funcs)

        return satisfiedByNode

    # unused in dogtail 2.x
    def describeSearchResult(self):
        return ' or '.join(p.describeSearchResult() for p in self.predicates)


class RegexPredicate(GenericPredicate):
    def __init__(self, name=None, roleName=None):
        super().__init__(name=name, roleName=roleName)

        # Override TranslatableString of dogtail 1.x, so re.match works
        self.name = name
        # set common name
        self.role_name = roleName

        if not dogtail_1x:
            # dogtail 2.x
            self.satisfied_by_node = self._genCompareFunc()
        else:
            self.satisfiedByNode = self._genCompareFunc()

    def _genCompareFunc(self):
        def predicate_satisfied_by_node(node):
            """
            Simple comparison function that supports regex for strings.

            :param node: Accessible object.
            :type node: Atspi.Accessible

            :return: True or False based on given criteria.
            :rtype: bool
            """

            try:
                # Check if user wants to check name, and compare it with the given node.
                if self.name is not None and not re.fullmatch(self.name, node.name):
                    return False

                # Check if user wants to check role_name, and compare it with the given node.
                if self.role_name is not None and not re.fullmatch(self.role_name, node.roleName):
                    return False

                # There are no conflicting parameters, so the match is a success
                return True

            except Exception:
                return False

        return predicate_satisfied_by_node

@contextlib.contextmanager
def search_cutoff_count(temp_value):
    old_value = defaultCutoffCount
    try:
        if not dogtail_1x:
            old_value = config.search_cut_off_limit
            config.search_cut_off_limit = temp_value
        else:
            old_value = config.searchCutoffCount
            config.searchCutoffCount = temp_value
        yield
    finally:
        if not dogtail_1x:
            config.search_cut_off_limit = old_value
        else:
            config.searchCutoffCount = old_value


class Thunderbird:
    """
    Manages the state of a thunderbird instance
    """

    def __init__(self, tb_name, profile_dir, imap_pw):
        self.name = tb_name
        self.tb_cmd = [self.name]
        if profile_dir:
            self.tb_cmd.append('--profile')
            self.tb_cmd.append(profile_dir)
        self.imap_pw = imap_pw
        self.start()

    def start(self):
        env = os.environ.copy()
        env['GTK_MODULES'] = 'gail:atk-bridge'
        env['GNOME_ACCESSIBILITY'] = '1'
        null = open(os.devnull, 'r+')
        self.process = subprocess.Popen(
            self.tb_cmd, stdout=null, stdin=null, stderr=null, env=env)
        self.app = self._get_app()

    def _get_app(self):
        with search_cutoff_count(70):
            tb = tree.root.application('Thunderbird')
        return tb

    def get_version(self):
        try:
            res = subprocess.check_output([self.name, '--version'])
            version = res.decode('utf-8').replace('Thunderbird ', '').split('.')[0]
        except (subprocess.SubprocessError, IndexError):
            raise Exception('Cannot determine version')
        return int(version)

    def quit(self):
        self.app.menu('File').doActionNamed('click')
        self.app.menu('File').menuItem('Quit').doActionNamed('click')
        self.process.wait()

    def kill(self):
        self.process.terminate()


def retry_if_failed(max_tries):
    """ Decorator that repeats a function if any exception is thrown. Assumes
    the decorated function is generally idempotent (i.e. if ran multiple times
    consecutively or multiple partial times it leads to the same result as if
    ran only once)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tb = args[0]

            for retry in range(0, max_tries):
                try:
                    func(*args, **kwargs)
                    break # if successful
                except Exception as e:
                    if retry == max_tries-1:
                        raise e
                    else:
                        print("failed during setup in {}.\n Retrying".format(
                            func.__name__))
                        tb.kill()
                        tb.start()
        return wrapper
    return decorator


def get_key_fpr():
    try:
        cmd = '/usr/bin/qubes-gpg-client-wrapper -K --with-colons'
        res = subprocess.check_output(cmd.split(' '))
        keyid = res.decode('utf-8').split('\n')[1]
        keyid = keyid.split(':')[9]
        keyid = keyid[-16:]
    except (subprocess.SubprocessError, IndexError):
        raise Exception('Cannot determine keyid')
    return keyid


def export_pub_key():
    try:
        cmd = '/usr/bin/qubes-gpg-client-wrapper --armor --export --output /home/user/pub.asc'
        subprocess.check_output(cmd.split(' '))
    except subprocess.SubprocessError:
        raise Exception('Cannot export public key')

@retry_if_failed(max_tries=3)
def enter_imap_passwd(tb):
    try:
        pass_prompt = tb.app.findChild(orPredicate(
            GenericPredicate(name='Enter your password for user', roleName='frame'),
            GenericPredicate(name='Enter your password for user', roleName='dialog')
        ))
    except tree.SearchError:
        # check new mail so client can realize IMAP requires entering a password
        get_messages(tb, button_only=True)
    # password entry
    pass_prompt = tb.app.findChild(orPredicate(
        GenericPredicate(name='Enter your password for user', roleName='frame'),
        GenericPredicate(name='Enter your password for user', roleName='dialog')
    ))
    pass_textbox = pass_prompt.child(roleName='password text')
    rawinput.typeText(tb.imap_pw)
    time.sleep(0.5)
    pass_prompt.childNamed("Use Password Manager to remember this password.")\
               .doActionNamed('check')
    pass_prompt.button('OK').doActionNamed('press')

def accept_qubes_attachments(tb):
    try:
        qubes_att = tb.app.child(name='Qubes Attachments added', roleName='label')
        # give it some time to settle
        time.sleep(3)
        qubes_att.parent.button('Enable').doActionNamed('press')

        qubes_att = tb.app.findChild(RegexPredicate(
            name='Qubes Attachments has been added.*', roleName='label'))
        # give it some time to settle
        time.sleep(3)
        qubes_att.parent.button('Not now').doActionNamed('press')
    except tree.SearchError:
        pass


def open_account_setup(tb):
    edit = tb.app.menu('Edit')
    edit.doActionNamed('click')
    account_settings = edit.menuItem('Account Settings')
    account_settings.doActionNamed('click')

def close_account_setup(tb):
    file = tb.app.menu('File')
    file.doActionNamed('click')
    file.child('Close').doActionNamed('click')

class TBEntry(GenericPredicate):
    def __init__(self, name):
        super(TBEntry, self).__init__(name=name, roleName='entry')

def show_menu_bar(tb):
    with search_cutoff_count(20):
        app = tb.app.child(name='Application', roleName='menu bar')
        app.child(name='View', roleName='menu').doActionNamed('click')
        app.child(name='Toolbars', roleName='menu').doActionNamed('click')
        app.child(name='Menu Bar', roleName='check menu item').doActionNamed('click')

@retry_if_failed(max_tries=3)
def configure_openpgp_account(tb):
    keyid = get_key_fpr()
    export_pub_key()
    tb.app.child(name='Tools', roleName='menu').doActionNamed('click')
    tb.app.child(name='OpenPGP Key Manager', roleName='menu item').doActionNamed('click')
    key_manager = tb.app.findChild(orPredicate(
        GenericPredicate(name='OpenPGP Key Manager', roleName='dialog'),
        GenericPredicate(name='OpenPGP Key Manager', roleName='frame')))
    key_manager.child(name='File', roleName='menu').doActionNamed('click')
    key_manager.child(name='Import Public Key(s) From File',
                      roleName='menu item').doActionNamed('click')
    file_chooser = tree.root.findChild(
        RegexPredicate(name='Import OpenPGP Key File.*',
                         roleName='file chooser')
    )
    # wait for dialog to completely initialize, otherwise it may try to click
    # on "Home" before it is active.
    time.sleep(1)
    rawinput.click(*file_chooser.childNamed('Home').position)
    rawinput.click(*file_chooser.childNamed('pub.asc').position)
    file_chooser.childNamed('Open').doActionNamed('click')
    accept_dialog = tb.app.findChild(orPredicate(
        RegexPredicate(name='.*(%s).*' % keyid),
        RegexPredicate(name='.[0-9A-F]*%s' % keyid),
        RegexPredicate(name='ID: 0x%s' % keyid),
        )).parent.parent
    accept_dialog.findChild(RegexPredicate("Accepted.*")).doActionNamed("select")
    accept_dialog.findChild(RegexPredicate('OK|Import')).doActionNamed('press')
    tb.app.findChild(
        RegexPredicate('Success! Keys imported.*')
    ).findChild(RegexPredicate('OK|Close')).doActionNamed('press')
    rawinput.doubleClick(*key_manager.findChild(
        RegexPredicate(name='Qubes test <user@localhost>.*')).position)
    key_property = tb.app.findChild(orPredicate(
        RegexPredicate(name="Key Properties.*", roleName='frame'),
        RegexPredicate(name="Key Properties.*", roleName='dialog')))
    key_property.findChild(
        RegexPredicate(name="Yes, I['’]ve verified in person.*",
                         roleName='radio button')).doActionNamed('select')
    key_property.childNamed('OK').doActionNamed('press')
    key_manager.child(name='Close', roleName='menu item').doActionNamed(
        'click')


def get_messages(tb, button_only=False):
    tb.app.child('Get Messages', roleName='button').doActionNamed('press')
    if button_only:
        return
    tb.app.findChild(
        RegexPredicate(name='Inbox.*', roleName='tree item')
    ).doActionNamed('activate')


def attach(tb, compose_window, path):
    compose_window.button('Attach').doActionNamed('press')
    compose_window.button('Attach').findChild(
        RegexPredicate(name='File.*', roleName='menu item')
    ).doActionNamed('click')
    # for some reason on some thunderbird versions do not expose 'Attach File'
    # dialog through accessibility API, use xdotool instead
    file_chooser = tree.root.findChild(
        RegexPredicate(name='Attach File.*',
                         roleName='file chooser'))
    rawinput.keyCombo('<Ctrl>l')
    location = file_chooser.child(name='Location Layer')
    location.children[0].text = path
    time.sleep(1)
    rawinput.keyCombo('Return')


def send_email(tb, sign=False, encrypt=False, inline=False, attachment=None):
    with search_cutoff_count(20):
        write = tb.app.button('New Message')
    write.doActionNamed('press')
    compose = tb.app.findChild(RegexPredicate(name='Write: .*', roleName='frame'))
    to_entry = compose.findChild(TBEntry(name='To'))
    if not to_entry.focused:
        to_entry.grabFocus()
    rawinput.typeText('user@localhost')
    # lets thunderbird settle down on default values (after filling recipients)
    time.sleep(1)
    subject_entry = compose.findChild(
        orPredicate(GenericPredicate(name='Subject:', roleName='entry'),
                    TBEntry(name='Subject')))
    subject_entry.grabFocus()
    rawinput.typeText(subject)
    try:
        compose_document = compose.child(roleName='document web')
        try:
            compose_document.parent.doActionNamed('click')
        except tree.ActionNotSupported:
            compose_document.grabFocus()
        rawinput.typeText('This is test message')
    except tree.SearchError:
        compose.child(
            roleName='document frame').text = 'This is test message'
    security = compose.findChild(
        RegexPredicate(name='Security|OpenPGP', roleName='button'))
    security.doActionNamed('press')
    encrypt_button = security.findChild(RegexPredicate('Require Encryption|Encrypt'))
    if encrypt_button.checked != encrypt:
        encrypt_button.doActionNamed('click')
        security.doActionNamed('press')
    sign_button = security.findChild(RegexPredicate('Digitally Sign.*'))
    if sign_button.checked != sign:
        sign_button.doActionNamed('click')
    if attachment:
        attach(tb, compose, attachment)
    compose.button('Send').doActionNamed('press')
    config.searchCutoffCount = 5
    with search_cutoff_count(5):
        try:
            if encrypt:
                tb.app.dialog('Enable Protection of Subject?'). \
                    button('Protect subject').doActionNamed('press')
        except tree.SearchError:
            pass

    # Fail if something like a dialog box prevented the compose window to be
    # closed. Means no email was actually sent.
    config.searchCutoffCount = 1
    with search_cutoff_count(1):
        timeout = 40 # the "showing" state usually updates after 7 ~ 25 seconds
        failed_sending = False
        error_message="unknown"
        while compose.showing:
            timeout -= 1
            if timeout <= 0:
                failed_sending = True
            try:
                dialog = tb.app.findChild(RegexPredicate(name='.*', roleName='dialog'))
                error_message = dialog.child(roleName='label').text
                if error_message != 'Status:':
                    failed_sending = True
            except tree.SearchError:
                pass
            if failed_sending:
                raise Exception("Failed to send message with error '{}'"\
                        .format(error_message))
            time.sleep(1)


def receive_message(tb, signed=False, encrypted=False, attachment=None):
    get_messages(tb)
    if encrypted:
        config.searchCutoffCount = 5
        with search_cutoff_count(5):
            tb.app.findChild(RegexPredicate(name=r'user[^,]*, .*, \.\.\..*',
                     roleName='table row')).doActionNamed('clickAncestor')
    tb.app.findChild(RegexPredicate(name='.*{}.*'.format(subject),
                 roleName='table row')).doActionNamed('clickAncestor')
    # wait a little to TB decrypt/check the message
    time.sleep(2)
    # dogtail always add '$' at the end of regexp; and also "Escape all
    # parentheses, since grouping will never be needed here", so it can't be used
    # here either
    try:
        msg = tb.app.findChild(RegexPredicate(roleName='document web',
                       name=subject + '$|Encrypted Message|\.\.\.'))
    except tree.SearchError:
        msg = tb.app.findChild(RegexPredicate(roleName='document frame',
                       name=subject + '$|Encrypted Message|\.\.\.'))
    try:
        msg = msg.child(roleName='section')
        if len(msg.text) < 5 and msg.children:
            msg = msg.children[0]
    except tree.SearchError:
        msg = msg.child(roleName='paragraph')
    msg_body = msg.text
    print('Message body: {}'.format(msg_body))
    assert msg_body.strip() == 'This is test message'
    #    if msg.children:
    #        msg_body = msg.children[0].text
    #    else:
    #        msg_body = msg.text
    with search_cutoff_count(5):
        try:
            if signed or encrypted:
                tb.app.findChild(RegexPredicate(name='OpenPGP.*', roleName='push button')).doActionNamed('press')
                # 'Message Security - OpenPGP' is an internal label,
                # nested 2 levels into the popup
                message_security = tb.app.child('Message Security - OpenPGP')
        except tree.SearchError:
            # alternative way of opening 'message security'
            rawinput.keyCombo('<Control><Alt>s')
            message_security = tb.app.child('Message Security - OpenPGP')
        message_security = message_security.parent.parent
        try:
            if signed:
                message_security.child('Good Digital Signature')
            if encrypted:
                message_security.child('Message Is Encrypted')
        except tree.SearchError:
            if signed or encrypted:
                raise
        message_security.parent.click()

    if attachment:
        # it can be either "1 attachment:" or "2 attachments"
        attachment_label = tb.app.findChild(RegexPredicate(name='.* attachment[:s]?', roleName='label'))
        offset = 0
        if attachment_label.name == '1 attachment:':
            offset += 1
        elif attachment_label.name == '1 attachment':
            offset += 2
        attachment_size = attachment_label.parent.children[
            attachment_label.indexInParent + 1 + offset]
        assert attachment_size.text[0] != '0'
        try:
            # TB >= 154
            attachment_save = attachment_label.parent.button('Save')
        except tree.SearchError:
            attachment_save_parent = attachment_label.parent.children[
                attachment_label.indexInParent + 2 + offset]
            attachment_save = attachment_save_parent.findChild(
                RegexPredicate(name='Save.*', roleName='push button'))
        try:
            # try child button first
            attachment_save.children[1].doActionNamed('press')
        except IndexError:
            # otherwise press main button to open the menu
            attachment_save.doActionNamed('press')
            # and choose "Save As..."
            attachment_save.findChild(
                RegexPredicate(name='Save As.*|Save All.*', roleName='menu item')
            ).doActionNamed('click')
        save_as = tree.root.findChild(
            RegexPredicate(name='Save All Attachments|Save Attachment.*',
                                roleName='file chooser'))
        rawinput.click(*save_as.childNamed('Home').position)
        rawinput.click(*save_as.childNamed('Desktop').position)
        save_as.childNamed('Save').doActionNamed('click')
        time.sleep(1)
        with open(attachment, 'r') as f:
            orig_attachment = f.read()
        saved_basepath = os.path.expanduser('~/Desktop/{}'.format(
            os.path.basename(attachment)))
        if os.path.exists(saved_basepath):
            with open(saved_basepath) as f:
                received_attachment = f.read()
            assert received_attachment == orig_attachment
            print("Attachment content ok")
        elif os.path.exists(saved_basepath + '.pgp'):
            p = subprocess.Popen(['qubes-gpg-client-wrapper'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 stdin=open(saved_basepath + '.pgp', 'r'))
            (stdout, stderr) = p.communicate()
            if signed:
                if b'Good signature' not in stderr:
                    print(stderr.decode())
                    raise AssertionError('no good signature found')
                print("Attachment signature ok")
            assert stdout.decode() == orig_attachment
            print("Attachment content ok - encrypted")
        else:
            raise Exception('Attachment {} not found'.format(saved_basepath))
        if os.path.exists(saved_basepath + '.sig'):
            p = subprocess.Popen(['qubes-gpg-client-wrapper', '--verify',
                                  saved_basepath + '.sig', saved_basepath],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (stdout, stderr) = p.communicate()
            if signed:
                if b'Good signature' not in stderr:
                    print(stderr.decode())
                    raise AssertionError('no good signature found')
                print("Attachment detached signature ok")

    # tb.app.button('Delete').doActionNamed('press')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tbname', help='Thunderbird executable name',
                        default='thunderbird')
    parser.add_argument('--profile', help='Thunderbird profile path')
    parser.add_argument('--imap_pw', help='IMAP password')
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('setup', help='setup Thunderbird for tests')
    parser_send_receive = subparsers.add_parser(
        'send_receive', help='send and receive an email')
    parser_send_receive.add_argument('--encrypted', action='store_true',
                                     default=False)
    parser_send_receive.add_argument('--signed', action='store_true',
                                     default=False)
    parser_send_receive.add_argument('--inline', action='store_true',
                                     default=False)
    parser_send_receive.add_argument('--with-attachment',
                                     action='store_true', default=False)
    args = parser.parse_args()

    # log only to stdout since logging to file have broken unicode support
    config.logDebugToFile = False

    tb = Thunderbird(args.tbname, args.profile, args.imap_pw)
    if args.command == 'setup':
        enter_imap_passwd(tb)
        accept_qubes_attachments(tb)
        show_menu_bar(tb)
        configure_openpgp_account(tb)
        tb.quit()
    if args.command == 'send_receive':
        if args.with_attachment:
            attachment = '/home/user/attachment{}.txt'.format(os.getpid())
            with open(attachment, 'w') as f:
                f.write('This is test attachment content')
        else:
            attachment = None
        send_email(tb, sign=args.signed, encrypt=args.encrypted,
                   inline=args.inline, attachment=attachment)
        time.sleep(5)

        receive_message(tb, signed=args.signed, encrypted=args.encrypted,
                        attachment=attachment)
        tb.quit()


if __name__ == '__main__':
    main()
