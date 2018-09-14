#!/usr/bin/python
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
from dogtail.predicate import GenericPredicate
from dogtail.config import config
import subprocess
import os
import time

subject = 'Test message {}'.format(os.getpid())

config.actionDelay = 0.5
config.searchCutoffCount = 10


def run(cmd):
    env = os.environ.copy()
    env['GTK_MODULES'] = 'gail:atk-bridge'
    null = open(os.devnull, 'r+')
    return subprocess.Popen(
            [cmd], stdout=null, stdin=null, stderr=null, env=env)


def get_app():
    config.searchCutoffCount = 20
    tb = tree.root.application('Thunderbird|Icedove')
    config.searchCutoffCount = 10
    return tb


def skip_autoconf(tb):
    # Thunderbird 52 flavor
    try:
        welcome = tb.childNamed('Welcome to .*')
        welcome.button(
            'I think I\'ll configure my account later.').\
            doActionNamed('press')
    except tree.SearchError:
        pass
    config.searchCutoffCount = 5
    # Icedove/Thunderbird 60+ flavor
    try:
        welcome = tb.childNamed('Mail Account Setup'
            '|Set Up an Existing Email Account')
        welcome.button('Cancel').doActionNamed('press')
    except tree.SearchError:
        pass
    # if enigmail is already installed
    try:
        tb.dialog('Enigmail Setup Wizard').button('Cancel').\
            doActionNamed('press')
        tb.dialog('Enigmail Alert').button('Close').doActionNamed('press')
    except tree.SearchError:
        pass
    config.searchCutoffCount = 10


def skip_system_integration(tb):
    try:
        integration = tb.childNamed('System Integration')
        integration.childNamed('Always perform .*').doActionNamed('uncheck')
        integration.button('Skip Integration').doActionNamed('press')
    except tree.SearchError:
        pass


def open_account_setup(tb):
    edit = tb.menu('Edit')
    edit.doActionNamed('click')
    account_settings = edit.menuItem('Account Settings')
    account_settings.doActionNamed('click')


class TBEntry(GenericPredicate):
    def __init__(self, name):
        super(TBEntry, self).__init__(name=name, roleName='entry')


def add_local_account(tb):
    open_account_setup(tb)
    settings = tb.dialog('Account Settings')
    settings.button('Account Actions').doActionNamed('press')
    settings.menuItem('Add Other Account.*').doActionNamed('click')
    wizard = tb.dialog('Account Wizard')
    wizard.childNamed('Unix Mailspool (Movemail)').doActionNamed('select')
    wizard.button('Next').doActionNamed('press')
    wizard.findChild(TBEntry('Your Name:')).text = 'Test'
    wizard.findChild(TBEntry('Email Address:')).text = 'user@localhost'
    wizard.button('Next').doActionNamed('press')
    # outgoing server
    wizard.button('Next').doActionNamed('press')
    # account name
    wizard.button('Next').doActionNamed('press')
    # summary
    wizard.button('Finish').doActionNamed('press')

    # set outgoing server
    settings.childNamed('Outgoing Server (SMTP)').doActionNamed('activate')
    settings.button('Add.*').doActionNamed('press')
    add_server = tb.dialog('SMTP Server')
    add_server.findChild(TBEntry('Description:')).text = 'localhost'
    add_server.findChild(TBEntry('Server Name:')).text = 'localhost'
    add_server.findChild(TBEntry('Port:')).text = '8025'
    add_server.menuItem('No authentication').doActionNamed('click')
    add_server.button('OK').doActionNamed('press')
    settings.button('OK').doActionNamed('press')

def install_enigmail_web_search(tb, search):
    '''Handle new addons manager search result which is just embedded
    addons.thunderbird.net website'''

    # search term
    search.children[0].text = 'enigmail'
    # search button
    search.children[1].doActionNamed('press')
    results = tb.child(
                name='enigmail :: Search :: Add-ons for Thunderbird',
                roleName='document web')

    # navigation on the website is fragile and ugly, but what we can do, the
    # old addons manager is gone
    # find "Enigmail" link, then navigate through the table to a column to its
    # right with "Add to Thunderbird link"
    enigmail_link = results.child(
                name='Enigmail',
                roleName='link')
    # Enigmail (link) -> Enigmail FEATURED (heading) -> '' (section) -> '' (section)
    # TODO: how to find next sibling? right now it relies on first result being the right one
    install_link = enigmail_link.parent.parent.parent.\
            children[1].child(name='Add to Thunderbird', roleName='link')
    install_link.doActionNamed('jump')
    # now confirmation dialog, it needs to have focus for 3 sec until "Install"
    # button will be active
    install_dialog = tb.dialog('Software Installation')
    install_dialog.button('Install Now').doActionNamed('press')

def install_enigmail_builtin(tb, search):
    '''Handle old, built-in search results browser'''
    # search term
    search.children[0].text = 'enigmail'
    # search button
    search.children[1].doActionNamed('press')

    addons = tb.findChild(
        GenericPredicate(name='Add-ons Manager', roleName='embedded'))
    enigmail = addons.findChild(
        GenericPredicate(name='Enigmail .*More.*', roleName='list item'))
    enigmail.button('Install').doActionNamed('press')
    config.searchCutoffCount = 5
    try:
        addons.button('Restart now').doActionNamed('press')
    except tree.SearchError:
        # no restart needed for this version
        addons_tab = tb.findChild(
            GenericPredicate(name='Add-ons Manager', roleName='page tab'))
        addons_tab.button('').doActionNamed('press')
        return
    finally:
        config.searchCutoffCount = 10

    tree.doDelay(5)
    tb = get_app()
    skip_system_integration(tb)

    tb.dialog('Enigmail Setup Wizard').button('Cancel').doActionNamed('press')
    tb.dialog('Enigmail Alert').button('Close').doActionNamed('press')

def install_enigmail(tb):
    tools = tb.menu('Tools')
    tools.doActionNamed('click')
    tools.menuItem('Add-ons').doActionNamed('click')
    addons = tb.findChild(
        GenericPredicate(name='Add-ons Manager', roleName='embedded'))
    # check if already installed
    addons.findChild(
        GenericPredicate(name='Extensions', roleName='list item')).\
        doActionNamed('')
    time.sleep(1)
    config.searchCutoffCount = 1
    try:
        addons_list = addons.findChildren(
                GenericPredicate(name='', roleName='list box'))[1]
        addons_list.childNamed('Enigmail.*')
    except tree.SearchError:
        pass
    else:
        # already installed
        return
    finally:
        config.searchCutoffCount = 10
    search = addons.findChild(
        GenericPredicate(name='Search all add-ons|Search on addons.thunderbird.net', roleName='section'))
    if 'addons.thunderbird.net' in search.name:
        install_enigmail_web_search(tb, search)
    else:
        install_enigmail_builtin(tb, search)


def configure_enigmail_global(tb):
    # disable p≡p Junior before creating an account, see
    # https://sourceforge.net/p/enigmail/bugs/904/
    menu = tb.menu('Edit')
    menu.doActionNamed('click')
    menu.menuItem('Preferences').doActionNamed('click')
    preferences = tb.findChild(
        GenericPredicate(name='Thunderbird Preferences', roleName='frame'))
    try:
        preferences.findChild(
            GenericPredicate(name='Privacy', roleName='list item')).\
            doActionNamed('')
    except tree.SearchError:
        preferences.findChild(
            GenericPredicate(name='Privacy', roleName='radio button')). \
            doActionNamed('select')
    preferences.findChild(
        GenericPredicate(name='Force using S/MIME and Enigmail', roleName='radio button')).\
        doActionNamed('select')
    preferences.button('Close').doActionNamed('press')

    menu = tb.menu('Enigmail')
    menu.doActionNamed('click')
    menu.menuItem('Preferences').doActionNamed('click')

    enigmail_prefs = tb.dialog('Enigmail Preferences')
    # wait for dialog to really initialize, otherwise it may load defaults
    # over just set values
    time.sleep(1)
    try:
        enigmail_prefs.findChild(GenericPredicate(name='Override with',
            roleName='check box')).doActionNamed('check')
        enigmail_prefs.findChild(GenericPredicate(name='Override with',
            roleName='section')).children[
            0].text = '/usr/bin/qubes-gpg-client-wrapper'
    except tree.ActionNotSupported:
        pass

    enigmail_prefs.button('OK').doActionNamed('press')
    config.searchCutoffCount = 5
    try:
        agent_alert = tb.dialog('Enigmail Alert')
        if 'Cannot connect to gpg-agent' in agent_alert.description:
            agent_alert.childNamed('Do not show.*').doActionNamed('check')
            agent_alert.button('OK').doActionNamed('press')
        else:
            raise Exception('Unknown alert: {}'.format(agent_alert.description))
    except tree.SearchError:
        pass
    finally:
        config.searchCutoffCount = 10


def configure_enigmail_account(tb):
    open_account_setup(tb)
    settings = tb.dialog('Account Settings')
    # assume only one account...
    settings.childNamed('OpenPGP Security').doActionNamed('activate')
    try:
        settings.childNamed('Enable OpenPGP.*').doActionNamed('check')
    except tree.ActionNotSupported:
        pass
    settings.button('OK').doActionNamed('press')

def attach(tb, compose_window, path):
    compose_window.button('Attach').button('Attach').doActionNamed('press')
    compose_window.button('Attach').menuItem('File.*').doActionNamed('click')
    # for some reason on some thunderbird versions do not expose 'Attach File'
    # dialog through accessibility API, use xdotool instead
    subprocess.check_call(
            ['xdotool', 'search', '--sync', '--name', 'Attach File.*',
             'key', '--window', '0', 'ctrl+l',
             'type', '--window', '%1', path])
    time.sleep(1)
    subprocess.check_call(
            ['xdotool', 'search', '--name', 'Attach File.*', 'key', 'Return'])
    time.sleep(1)
    #select_file = tb.dialog('Attach File.*')
    #places = select_file.findChild(GenericPredicate(roleName='table',
    #    name='Places'))
    #places.findChild(GenericPredicate(name='Desktop')).click()
    #location_toggle = select_file.findChild(GenericPredicate(roleName='toggle button',
    #    name='Type a file name'))
    #if not location_toggle.checked:
    #    location_toggle.doActionNamed('click')
    #location_label = select_file.child(name='Location:', roleName='label')
    #location = location_label.parent.children[location_label.indexInParent + 1]
    #location.text = path
    #select_file.button('Open').doActionNamed('click')

def send_email(tb, sign=False, encrypt=False, inline=False, attachment=None):
    tb.findChild(GenericPredicate(roleName='page tab list')).children[
        0].doActionNamed('switch')
    write = tb.button('Write')
    write.doActionNamed('press')
    # write.menuItem('Message').doActionNamed('click')
    tb.button('Write').menuItem('Message').doActionNamed('click')
    compose = tb.findChild(GenericPredicate(name='Write: .*', roleName='frame'))
    to = compose.findChild(
        GenericPredicate(name='To:', roleName='autocomplete'))
    to.findChild(GenericPredicate(roleName='entry')).text = 'user@localhost'
    compose.findChild(TBEntry('Subject:')).text = subject
    try:
        compose_document = compose.findChild(GenericPredicate(
            roleName='document web'))
        compose_document.parent.doActionNamed('click')
        compose_document.typeText('This is test message')
    except tree.SearchError:
        compose.findChild(GenericPredicate(
            roleName='document frame')).text = 'This is test message'
    # lets thunderbird settle down on default values (after filling recipients)
    time.sleep(1)
    try:
        sign_button = compose.button('Sign Message')
        encrypt_button = compose.button('Encrypt Message')
    except tree.SearchError:
        # old thunderbird/enigmail
        compose.button('Enigmail Encryption Info').doActionNamed('press')
        sign_encrypt = tb.dialog('Enigmail Encryption & Signing Settings')
        encrypt_checkbox = sign_encrypt.childNamed('Encrypt Message')
        if encrypt_checkbox.checked != encrypt:
            encrypt_checkbox.doActionNamed(encrypt_checkbox.actions.keys()[0])
        sign_checkbox = sign_encrypt.childNamed('Sign Message')
        if sign_checkbox.checked != sign:
            sign_checkbox.doActionNamed(sign_checkbox.actions.keys()[0])
        if inline:
            sign_encrypt.childNamed('Use Inline PGP').doActionNamed('select')
        else:
            sign_encrypt.childNamed('Use PGP/MIME').doActionNamed('select')
        sign_encrypt.button('OK').doActionNamed('press')
    else:
        if ('ON' in sign_button.description) != sign:
            sign_button.doActionNamed('press')
        if ('ON' in encrypt_button.description) != encrypt:
            encrypt_button.doActionNamed('press')
        if inline:
            enigmail_menu = compose.menu('Enigmail')
            enigmail_menu.doActionNamed('click')
            enigmail_menu.menuItem('Protocol: Inline PGP').doActionNamed('click')

    if attachment:
        attach(tb, compose, attachment)
    compose.button('Send').doActionNamed('press')
    if inline and attachment:
        tb.dialog('Enigmail Prompt').button('OK').doActionNamed('press')
    config.searchCutoffCount = 5
    try:
        if encrypt:
            tb.dialog('Enable Protection of Subject?').\
                button('Protect subject').doActionNamed('press')
    except tree.SearchError:
        pass
    finally:
        config.searchCutoffCount = 10


def receive_message(tb, signed=False, encrypted=False, attachment=None):
    tb.findChild(GenericPredicate(name='user@localhost',
        roleName='table row')).doActionNamed('activate')
    tb.button('Get Messages').doActionNamed('press')
    tb.menuItem('Get All New Messages').doActionNamed('click')
    tb.findChild(
        GenericPredicate(name='Inbox.*', roleName='table row')).doActionNamed(
        'activate')
    config.searchCutoffCount = 3
    try:
        tb.findChild(GenericPredicate(name='Encrypted Message .*',
            roleName='table row')).doActionNamed('activate')
    except tree.SearchError:
        pass
    finally:
        config.searchCutoffCount = 10
    tb.findChild(GenericPredicate(name='.*{}.*'.format(subject),
        roleName='table row')).doActionNamed('activate')
    # wait a little to TB decrypt/check the message
    time.sleep(2)
    # dogtail always add '$' at the end of regexp; and also "Escape all
    # parentheses, since grouping will never be needed here", so it can't be used
    # here either
    try:
        msg = tb.findChild(GenericPredicate(roleName='document web',
            name=subject + '$|Encrypted Message'))
    except tree.SearchError:
        msg = tb.findChild(GenericPredicate(roleName='document frame',
            name=subject + '$|Encrypted Message'))
    try:
        msg = msg.findChild(GenericPredicate(roleName='section')).children[0]
    except tree.SearchError:
        msg = msg.findChild(GenericPredicate(roleName='paragraph'))
    msg_body = msg.text
    print 'Message body: {}'.format(msg_body)
    assert msg_body.strip() == 'This is test message'
    #    if msg.children:
    #        msg_body = msg.children[0].text
    #    else:
    #        msg_body = msg.text
    config.searchCutoffCount = 5
    try:
        details = tb.button('Details')
        enigmail_status = details.parent.children[details.indexInParent - 1]
        print 'Enigmail status: {}'.format(enigmail_status.text)
        if signed:
            assert 'Good signature from' in enigmail_status.text
        if encrypted:
            assert 'Decrypted message' in enigmail_status.text
    except tree.SearchError:
        if signed or encrypted:
            raise
    finally:
        config.searchCutoffCount = 10

    if attachment:
        # it can be either "1 attachment:" or "2 attachments"
        attachment_label = tb.child(name='.* attachment[:s]', roleName='label')
        offset = 0
        if attachment_label.name == '1 attachment:':
            offset += 1
        attachment_size = attachment_label.parent.children[
            attachment_label.indexInParent + 1 + offset]
        assert attachment_size.text[0] != '0'
        attachment_label.parent.children[
            attachment_label.indexInParent + 2 + offset].\
            button('Save.*').children[1].doActionNamed('press')
        # for some reason on some thunderbird versions do not expose 'Attach File'
        # dialog through accessibility API, use xdotool instead
        subprocess.check_call(
                ['xdotool', 'search', '--name', 'Save Attachment',
                 'key', '--window', '0', '--delay', '30ms', 'ctrl+l', 'Home',
                 'type', '~/Desktop/\r'])
        #save_as = tb.dialog('Save .*Attachment.*')
        #places = save_as.findChild(GenericPredicate(roleName='table',
        #    name='Places'))
        #places.findChild(GenericPredicate(name='Desktop')).click()
        #if 'attachments' in attachment_label.text:
        #    save_as.button('Open').doActionNamed('click')
        #else:
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
            print "Attachment content ok"
        elif os.path.exists(saved_basepath + '.pgp'):
            p = subprocess.Popen(['qubes-gpg-client-wrapper'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=open(saved_basepath + '.pgp', 'r'))
            (stdout, stderr) = p.communicate()
            if signed:
                if 'Good signature' not in stderr:
                    print(stderr)
                    raise AssertionError('no good signature found')
                print "Attachment signature ok"
            assert stdout == orig_attachment
            print "Attachment content ok - encrypted"
        else:
            raise Exception('Attachment {} not found'.format(saved_basepath))
        if os.path.exists(saved_basepath + '.sig'):
            p = subprocess.Popen(['qubes-gpg-client-wrapper', '--verify',
                saved_basepath + '.sig', saved_basepath],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (stdout, stderr) = p.communicate()
            if signed:
                assert 'Good signature' in stderr
                print "Attachment detached signature ok"

    # tb.button('Delete').doActionNamed('press')


def quit_tb(tb):
    tb.button('AppMenu').doActionNamed('press')
    tb.menu('AppMenu').menuItem('Quit').doActionNamed('click')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tbname', help='Thunderbird executable name',
        default='thunderbird')
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('setup', help='setup Thunderbird for tests')
    parser_send_receive = subparsers.add_parser('send_receive',
        help='send and receive an email')
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

    if args.command == 'setup':
        proc = run(args.tbname)
        tb = get_app()
        skip_autoconf(tb)
        install_enigmail(tb)
        configure_enigmail_global(tb)
        quit_tb(tb)
        subprocess.call(['pkill', 'pep-json-server'])
        proc.wait()
        proc = run(args.tbname)
        tb = get_app()
        skip_autoconf(tb)
        add_local_account(tb)
        configure_enigmail_account(tb)
    if args.command == 'send_receive':
        tb = get_app()
        if args.with_attachment:
            attachment = '/home/user/attachment{}.txt'.format(os.getpid())
            with open(attachment, 'w') as f:
                f.write('This is test attachment content')
        else:
            attachment = None
        send_email(tb, sign=args.signed, encrypt=args.encrypted, inline=args.inline,
            attachment=attachment)
        time.sleep(5)
        receive_message(tb, signed=args.signed, encrypted=args.encrypted,
            attachment=attachment)
        quit_tb(tb)

if __name__ == '__main__':
    main()
