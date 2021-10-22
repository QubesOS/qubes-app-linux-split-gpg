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

from dogtail import tree
from dogtail.predicate import GenericPredicate, Predicate
from dogtail.config import config
from dogtail.rawinput import click, doubleClick, keyCombo
import subprocess
import os
import time
import functools

subject = 'Test message {}'.format(os.getpid())

defaultCutoffCount = 10

config.actionDelay = 1.0
config.defaultDelay = 1.0
config.searchCutoffCount = defaultCutoffCount


class orPredicate(Predicate):
    def __init__(self, *predicates):
        self.predicates = predicates
        self.satisfiedByNode = self._genCompareFunc()

    def _genCompareFunc(self):
        funcs = [p.satisfiedByNode for p in self.predicates]

        def satisfiedByNode(node):
            return any(f(node) for f in funcs)

        return satisfiedByNode

    def describeSearchResult(self):
        return ' or '.join(p.describeSearchResult() for p in self.predicates)

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
        null = open(os.devnull, 'r+')
        self.process = subprocess.Popen(
            self.tb_cmd, stdout=null, stdin=null, stderr=null, env=env)
        self.app = self._get_app()

    def _get_app(self):
        config.searchCutoffCount = 50
        tb = tree.root.application('Thunderbird|Icedove')
        config.searchCutoffCount = defaultCutoffCount
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
                    if retry == max_tries:
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

def enter_imap_passwd(tb):
    # check new mail so client can realize IMAP requires entering a password
    get_messages(tb)
    # password entry
    pass_prompt = tb.app.child(name='Enter your password for user', roleName='dialog')
    pass_textbox = pass_prompt.findChild(GenericPredicate(roleName='password text'))
    pass_textbox.text = tb.imap_pw
    pass_prompt.childNamed("Use Password Manager to remember this password.")\
               .doActionNamed('check')
    pass_prompt.findChild(orPredicate(
        GenericPredicate(name='OK', roleName='push button'),       # tb < 91
        GenericPredicate(name='Sign in', roleName='push button'))  # tb >= 91
    ).doActionNamed('press')

def accept_qubes_attachments(tb):
    try:
        qubes_att = tb.app.child(name='Qubes Attachments added', roleName='label')
        # give it some time to settle
        time.sleep(3)
        qubes_att.parent.button('Enable').doActionNamed('press')

        qubes_att = tb.app.child(name='Qubes Attachments has been added.*', roleName='label')
        # give it some time to settle
        time.sleep(3)
        qubes_att.parent.button('Not now').doActionNamed('press')
    except tree.SearchError:
        pass
    config.searchCutoffCount = defaultCutoffCount


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
    config.searchCutoffCount = 20
    app = tb.app.findChild(
        GenericPredicate(name='Application', roleName='menu bar'))
    app.findChild(GenericPredicate(
        name='View', roleName='menu')).doActionNamed('click')
    app.findChild(GenericPredicate(
        name='Toolbars', roleName='menu')).doActionNamed('click')
    app.findChild(GenericPredicate(
        name='Menu Bar', roleName='check menu item')).doActionNamed('click')
    config.searchCutoffCount = defaultCutoffCount

@retry_if_failed(max_tries=3)
def configure_openpgp_account(tb):
    keyid = get_key_fpr()
    export_pub_key()
    open_account_setup(tb)
    settings = tb.app.findChild(orPredicate(
        GenericPredicate(name='Account Settings.*', roleName='frame'),
        GenericPredicate(name='Account Settings', roleName='dialog'),
    ))
    # assume only one account...
    settings.childNamed('End-To-End Encryption').doActionNamed('activate')
    settings.childNamed('Add Key.*').doActionNamed('press')
    settings.childNamed('Use your external key.*').doActionNamed('select')
    settings.childNamed('Continue').doActionNamed('press')
    settings.findChild(TBEntry('123456789.*')).text = keyid
    settings.button('Save key ID').doActionNamed('press')
    settings.findChild(GenericPredicate(name='0x%s.*' % keyid,
                                        roleName='radio button')).doActionNamed(
        'select')
    settings.childNamed('OpenPGP Key Manager.*').doActionNamed('press')
    key_manager = tb.app.findChild(
        GenericPredicate(name='OpenPGP Key Manager', roleName='frame'))
    key_manager.findChild(
        GenericPredicate(name='File', roleName='menu')).doActionNamed('click')
    key_manager.findChild(
        GenericPredicate(name='Import Public Key(s) From File',
                         roleName='menu item')).doActionNamed('click')
    file_chooser = tb.app.findChild(GenericPredicate(name='Import OpenPGP Key File',
                                                 roleName='file chooser'))
    # wait for dialog to completely initialize, otherwise it may try to click
    # on "Home" before it is active.
    time.sleep(1)
    click(*file_chooser.childNamed('Home').position)
    click(*file_chooser.childNamed('pub.asc').position)
    file_chooser.childNamed('Open').doActionNamed('click')
    accept_dialog = tb.app.findChild(orPredicate(
        GenericPredicate(name='.*(%s).*' % keyid),
        GenericPredicate(name='.[0-9A-F]*%s' % keyid),
        )).parent
    accept_dialog.childNamed('OK').doActionNamed('press')
    tb.app.childNamed('Success! Keys imported.*').childNamed('OK').doActionNamed(
        'press')
    doubleClick(*key_manager.findChild(
        GenericPredicate(name='Qubes test <user@localhost>.*')).position)
    key_property = tb.app.findChild(
        GenericPredicate(name="Key Properties.*", roleName='frame'))
    key_property.findChild(
        GenericPredicate(name="Yes, I['’]ve verified in person.*",
                         roleName='radio button')).doActionNamed('select')
    key_property.childNamed('OK').doActionNamed('press')
    key_manager.findChild(
        GenericPredicate(name='Close', roleName='menu item')).doActionNamed(
        'click')
    close_account_setup(tb)


def get_messages(tb):
    tb.app.child(name='user@localhost',
            roleName='table row').doActionNamed('activate')
    tb.app.button('Get Messages').doActionNamed('press')
    tb.app.menuItem('Get All New Messages').doActionNamed('click')
    tb.app.child(name='Inbox.*', roleName='table row').doActionNamed(
        'activate')

def attach(tb, compose_window, path):
    compose_window.button('Attach').button('Attach').doActionNamed('press')
    compose_window.button('Attach').menuItem('File.*').doActionNamed('click')
    # for some reason on some thunderbird versions do not expose 'Attach File'
    # dialog through accessibility API, use xdotool instead
    subprocess.check_call(
        ['xdotool', 'search', '--sync', '--name', 'Attach File.*',
         'key', '--window', '0', 'ctrl+l',
         'sleep', '1',
         'type', '--window', '%1', path])
    time.sleep(1)
    subprocess.check_call(
        ['xdotool', 'search', '--name', 'Attach File.*', 'key', 'Return'])
    time.sleep(1)
    # select_file = tb.app.dialog('Attach File.*')
    # places = select_file.child(roleName='table',
    #    name='Places')
    # places.child(name='Desktop').click()
    # location_toggle = select_file.child(roleName='toggle button',
    #    name='Type a file name')
    # if not location_toggle.checked:
    #    location_toggle.doActionNamed('click')
    # location_label = select_file.child(name='Location:', roleName='label')
    # location = location_label.parent.children[location_label.indexInParent + 1]
    # location.text = path
    # select_file.button('Open').doActionNamed('click')


def send_email(tb, sign=False, encrypt=False, inline=False, attachment=None):
    config.searchCutoffCount = 20
    write = tb.app.button('Write')
    config.searchCutoffCount = defaultCutoffCount
    write.doActionNamed('press')
    compose = tb.app.child(name='Write: .*', roleName='frame')
    to_entry = compose.findChild(TBEntry(name='To'))
    to_entry.text = 'user@localhost'
    # lets thunderbird settle down on default values (after filling recipients)
    time.sleep(1)
    subject_entry = compose.findChild(
        orPredicate(GenericPredicate(name='Subject:', roleName='entry'),
                    TBEntry(name='Subject')))
    subject_entry.text = subject
    try:
        compose_document = compose.child(roleName='document web')
        try:
            compose_document.parent.doActionNamed('click')
        except tree.ActionNotSupported:
            pass
        compose_document.typeText('This is test message')
    except tree.SearchError:
        compose.child(
            roleName='document frame').text = 'This is test message'
    security = compose.findChild(
        GenericPredicate(name='Security', roleName='push button'))
    security.doActionNamed('press')
    sign_button = security.childNamed('Digitally Sign This Message')
    encrypt_button = security.childNamed('Require Encryption')
    if sign_button.checked != sign:
        sign_button.doActionNamed('click')
    if encrypt_button.checked != encrypt:
        encrypt_button.doActionNamed('click')
    if attachment:
        attach(tb, compose, attachment)
    compose.button('Send').doActionNamed('press')
    config.searchCutoffCount = 5
    try:
        if encrypt:
            tb.app.dialog('Enable Protection of Subject?'). \
                button('Protect subject').doActionNamed('press')
    except tree.SearchError:
        pass
    finally:
        config.searchCutoffCount = defaultCutoffCount


def receive_message(tb, signed=False, encrypted=False, attachment=None):
    get_messages(tb)
    config.searchCutoffCount = 5
    try:
        tb.app.child(name='Encrypted Message .*|.*\.\.\. .*',
                 roleName='table row').doActionNamed('activate')
    except tree.SearchError:
        pass
    finally:
        config.searchCutoffCount = defaultCutoffCount
    tb.app.child(name='.*{}.*'.format(subject),
             roleName='table row').doActionNamed('activate')
    # wait a little to TB decrypt/check the message
    time.sleep(2)
    # dogtail always add '$' at the end of regexp; and also "Escape all
    # parentheses, since grouping will never be needed here", so it can't be used
    # here either
    try:
        msg = tb.app.child(roleName='document web',
                       name=subject + '$|Encrypted Message|\.\.\.')
    except tree.SearchError:
        msg = tb.app.child(roleName='document frame',
                       name=subject + '$|Encrypted Message|\.\.\.')
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
    config.searchCutoffCount = 5
    try:
        if signed or encrypted:
            tb.app.button('OpenPGP.*').doActionNamed('press')
            # 'Message Security - OpenPGP' is an internal label,
            # nested 2 levels into the popup
            message_security = tb.app.child('Message Security - OpenPGP')
    except tree.SearchError:
        # alternative way of opening 'message security'
        keyCombo('<Control><Alt>s')
        message_security = tb.app.child('Message Security - OpenPGP')
    finally:
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
    config.searchCutoffCount = defaultCutoffCount

    if attachment:
        # it can be either "1 attachment:" or "2 attachments"
        attachment_label = tb.app.child(name='.* attachment[:s]', roleName='label')
        offset = 0
        if attachment_label.name == '1 attachment:':
            offset += 1
        attachment_size = attachment_label.parent.children[
            attachment_label.indexInParent + 1 + offset]
        assert attachment_size.text[0] != '0'
        attachment_save = attachment_label.parent.children[
            attachment_label.indexInParent + 2 + offset].button('Save.*')
        try:
            # try child button first
            attachment_save.children[1].doActionNamed('press')
        except IndexError:
            # otherwise press main button to open the menu
            attachment_save.doActionNamed('press')
            # and choose "Save As..."
            attachment_save.menuItem('Save As.*|Save All.*').doActionNamed(
                'click')
        # for some reasons some Thunderbird versions do not expose 'Attach File'
        # dialog through accessibility API, use xdotool instead
        save_as = tb.app.findChild(
            GenericPredicate(name='Save All Attachments',
                                roleName='file chooser'))
        click(*save_as.childNamed('Home').position)
        click(*save_as.childNamed('Desktop').position)
        save_as.childNamed('Open').doActionNamed('click')
        # save_as = tb.app.dialog('Save .*Attachment.*')
        # places = save_as.child(roleName='table',
        #    name='Places')
        # places.child(name='Desktop').click()
        # if 'attachments' in attachment_label.text:
        #    save_as.button('Open').doActionNamed('click')
        # else:
        #    save_as.button('Save').doActionNamed('click')
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
        tb.quit()
        subprocess.call(['pkill', 'pep-json-server'])
        tb.start()
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
