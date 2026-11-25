#!/usr/bin/python3
#  -*- encoding: utf-8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2018 Marek Marczykowski-Górecki
#                               <marmarek@invisiblethingslab.com>
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
# with this program; if not, see <http://www.gnu.org/licenses/>.
import argparse

import dogtail
from dogtail import tree, predicate, rawinput
from dogtail.config import config
import subprocess
import os
import re
import time

subject = 'Test message {}'.format(os.getpid())

dogtail_1x = dogtail.__version__.startswith(("0.", "1."))

defaultCutoffCount = 10

if not dogtail_1x:
    config.action_delay = 0.5
    config.search_cut_off_limit = defaultCutoffCount
else:
    config.actionDelay = 0.5
    config.searchCutoffCount = defaultCutoffCount


def run(cmd):
    env = os.environ.copy()
    env['GTK_MODULES'] = 'gail:atk-bridge'
    return subprocess.Popen([cmd], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)


def get_app():
    app = tree.root.application('org.gnome.Evolution')
    return app

def open_preferences(app):
    edit = app.menu('Edit')
    edit.menuItem('Preferences').doActionNamed('click')

def open_accounts(app):
    open_preferences(app)
    settings = app.findChild(lambda node:
        node.name == 'Evolution Preferences' and node.roleName == 'frame')
    accounts_tab = settings.child('Account Name').parent.parent
    return settings, accounts_tab

def get_sibling_offset(node, offset):
    return node.parent.children[node.indexInParent+offset]

def get_sibling_button_maybe(button):
    try:
        # if there is a sibling button (without the name) that's the one that works
        button_sibling = button.parent.children[button.indexInParent + 1]
        if button_sibling.roleName == "push button":
            return button_sibling
    except KeyError:
        pass
    return button

def add_local_account(app):
    accounts_tab = None
    settings = None
    try:
        wizard = app.childNamed('Welcome')
    except tree.SearchError:
        settings, accounts_tab = open_accounts(app)
        accounts_tab.button('Add').doActionNamed('click')
        wizard = app.window('Welcome')
    # Welcome tab
    wizard.button('Next').doActionNamed('click')
    # Restore from backup, if launched from startup wizard
    if wizard.name == 'Restore from Backup':
        wizard.button('Next').doActionNamed('click')
    # Identity tab
    wizard.childLabelled('Full Name:').text = 'Test'
    wizard.childLabelled('Email Address:').text = 'user@localhost'
    wizard.button('Next').doActionNamed('click')
    # Receiving Email tab
    server_type = wizard.child('Server Type:')
    for i in range(60):
        if server_type.showing:
            break
        time.sleep(0.5)
    assert server_type.showing
    wizard.menuItem('Maildir-format mail directories').doActionNamed('click')
    # showingOnly=True doesn't work in dogtail 2.x
    #wizard.childLabelled('Mail Directory:', showingOnly=True)
    m_dir = wizard.findChild(
        lambda node: node.name == 'Mail Directory:' and
                     node.roleName == 'label' and
                     node.showing
    )
    m_dir.parent.menuItem('Other…').doActionNamed('click')
    file_chooser = app.child('Choose a Maildir mail directory',
        roleName='file chooser')
    file_chooser.child('File System Root').doActionNamed('click')
    file_chooser.child('home').doActionNamed('activate')
    file_chooser.child('user').doActionNamed('activate')
    file_chooser.child('Mail').doActionNamed('activate')
    file_chooser.button('Open').doActionNamed('click')
    time.sleep(1)
    wizard.button('Next').doActionNamed('click')
    # Receiving Options tab
    wizard.button('Next').doActionNamed('click')
    # Sending Email tab
    sending = wizard.child('Sending Email',
        roleName=wizard.children[0].roleName)
    sending.childLabelled('Server:').text = 'localhost'
    sending.childLabelled('Port:').child(roleName='text').text = '8025'
    encryption = sending.childLabelled('Encryption method:')
    if encryption.name != 'No encryption':
        encryption.combovalue = 'No encryption'
    wizard.button('Next').doActionNamed('click')
    # Account Summary tab
    wizard.button('Next').doActionNamed('click')
    # Done tab
    wizard.button('Apply').doActionNamed('click')

    if not accounts_tab:
        settings, accounts_tab = open_accounts(app)
    # this selects the entry
    accounts_tab.child('user@localhost').doActionNamed('edit')
    # this open account settings
    accounts_tab.child('user@localhost').doActionNamed('activate')

    account = app.dialog('Account Editor')
    key_id = account.childLabelled('OpenPGP Key ID:')
    try:
        key_id = key_id.child(roleName='text')
    except tree.SearchError:
        pass
    key_id.text = 'user@localhost'

    ask = account.child('Ask before sending mails with own public key')
    ask.doActionNamed('click')

    account.button('OK').doActionNamed('click')

    # "modern" dialogs lack 'Close' button, and dogtail seems to not support
    # sending window close action; use xdotool as a workaround
    subprocess.call(['xdotool', 'search', settings.name, 'windowclose'])


def attach(app, compose_window, path):
    compose_window.findChild(
        lambda node: re.match(r'Add Attachment.*', node.name) and
                     node.roleName == 'button'
    ).click()
    file_chooser = app.child('Add Attachment', roleName='file chooser')
    file_chooser.child('Home').click()
    file_chooser.child(os.path.basename(path)).click()
    file_chooser.button('Attach').doActionNamed('click')

def send_email(app, sign=False, encrypt=False, inline=False, attachment=None):
    new_button = app.button('New')
    new_button = get_sibling_button_maybe(new_button)
    new_button.doActionNamed('click')
    new_message = app.child('Compose Message', roleName='frame')
    new_message.textentry('To:').text = 'user@localhost,'
    new_message.childLabelled('Subject:').text = subject
    compose_document = new_message.child(
        roleName='document web')
    compose_document.click()
    rawinput.typeText('This is test message')
    if encrypt:
        new_message.menu('Options').child('PGP Encrypt', roleName='check menu item').doActionNamed(
            'click')
    if sign:
        new_message.menu('Options').child('PGP Sign', roleName='check menu item').doActionNamed('click')
    if inline:
        raise NotImplementedError(
            'toggling inline pgp not supported for evolution')
    if attachment:
        attach(app, new_message, attachment)

    new_message.button('Send').doActionNamed('click')

def receive_message(app, signed=False, encrypted=False, attachment=None):
    send_receive = app.button('Send / Receive')
    send_receive = get_sibling_button_maybe(send_receive)
    send_receive.doActionNamed('click')
    app.findChild(lambda node:
        node.name.startswith('Inbox ') and node.roleName== 'table cell'
    ).doActionNamed('edit')
    messages = app.child('Messages', roleName='panel')
    messages.child(subject).grabFocus()
    message = app.child('Evolution Mail Display', roleName='document web')
    msg_body = message.findChild(lambda node:
        re.match(r'.message.*', node.name) and node.roleName == 'document web')\
        .children[0].text
    print('Message body: "{}"'.format(msg_body))
    assert msg_body.strip() == 'This is test message'

    try:
        gpg_header = message.findChildren(lambda cell:
            cell.roleName == 'row header' and 'Security' in cell.text)[0]
        gpg_info = gpg_header.parent[gpg_header.indexInParent+1].text
    except (tree.SearchError, IndexError):
        # From, To, Subject, Date, Security
        gpg_info = message.findChildren(
            predicate.GenericPredicate(roleName='table cell'))[4].text
    print('GPG info: {}'.format(gpg_info))

    if signed:
        assert 'signed' in gpg_info
    if encrypted:
        assert 'encrypted' in gpg_info

    if attachment:
        # check if attachment is present
        messages.parent.parent.child(os.path.basename(attachment))
        messages.parent.parent.button('Save As').click()

        save_dialog = app.child('Save Attachment', roleName='file chooser')
        saved_basepath = os.path.expanduser('~/Desktop/{}'.format(
            os.path.basename(attachment)))
        save_dialog.child(roleName='text').text = saved_basepath
        save_dialog.button('Save').doActionNamed('click')

        time.sleep(1)
        with open(attachment, 'r') as f:
            orig_attachment = f.read()
        if os.path.exists(saved_basepath):
            with open(saved_basepath) as f:
                received_attachment = f.read()
            assert received_attachment == orig_attachment
            print("Attachment content ok")
        else:
            raise Exception('Attachment {} not found'.format(saved_basepath))

def quit(app):
    app.menu('File').menuItem('Quit').doActionNamed('click')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', help='Evolution executable name',
        default='evolution')
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('setup', help='setup Evolution for tests')
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
    if not dogtail_1x:
        config.debug_file = "None"
    else:
        config.logDebugToFile = False

    if args.command == 'setup':
        subprocess.check_call([
            'gsettings', 'set', 'org.gnome.evolution-data-server',
            'camel-gpg-binary', '/usr/bin/qubes-gpg-client-wrapper'])
        subprocess.check_call([
            'gsettings', 'set', 'org.gnome.evolution.mail',
            'prompt-check-if-default-mailer', 'false'])
        proc = run(args.exe)
        app = get_app()
        add_local_account(app)
    if args.command == 'send_receive':
        app = get_app()
        if args.with_attachment:
            attachment = '/home/user/attachment{}.txt'.format(os.getpid())
            with open(attachment, 'w') as f:
                f.write('This is test attachment content')
        else:
            attachment = None
        send_email(app, sign=args.signed, encrypt=args.encrypted, inline=args.inline,
            attachment=attachment)
        time.sleep(5)
        receive_message(app, signed=args.signed, encrypted=args.encrypted,
            attachment=attachment)
        quit(app)

if __name__ == '__main__':
    main()
