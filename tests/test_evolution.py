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

from dogtail import tree, predicate
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
    return subprocess.Popen([cmd], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)


def get_app():
    config.searchCutoffCount = 30
    app = tree.root.application('evolution')
    config.searchCutoffCount = 10
    return app

def open_preferences(app):
    edit = app.menu('Edit')
    edit.menuItem('Preferences').doActionNamed('click')

def open_accounts(app):
    open_preferences(app)
    settings = app.window('Evolution Preferences')
    accounts_tab = settings.child(roleName='page tab list').children[1]
    config.searchCutoffCount = 3
    try:
        accounts_tab.child('Open Online Accounts')
    except tree.SearchError:
        accounts_tab = settings.child(roleName='page tab list').children[0]
    finally:
        config.searchCutoffCount = 10
    return settings, accounts_tab

def get_sibling_offset(node, offset):
    return node.parent.children[node.indexInParent+offset]

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
    time.sleep(2)
    wizard.menuItem('Local delivery').doActionNamed('click')
    wizard.childLabelled('Local Delivery File:').parent.button('(None)').\
        doActionNamed('click')
    file_chooser = app.child('Choose a local delivery file',
        roleName='file chooser')
    file_chooser.child('File System Root').doActionNamed('click')
    file_chooser.child('var').doActionNamed('activate')
    file_chooser.child('spool').doActionNamed('activate')
    file_chooser.child('mail').doActionNamed('activate')
    file_chooser.child('user').doActionNamed('activate')
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
    account.button('OK').doActionNamed('click')

    settings.button('Close').doActionNamed('click')


def attach(app, compose_window, path):
    compose_window.button('Add Attachment...').doActionNamed('click')
    # TODO: this fails, for some reason dogtail consider 'app' dead,
    # while the file chooser dialog can be inspected with sniff without any
    # problem
    file_chooser = app.child('Add Attachment', roleName='file chooser')
    file_chooser.child('Home').doActionNamed('click')
    file_chooser.child(os.path.basename(path)).doActionNamed('activate')
    file_chooser.button('Attach').doActionNamed('click')

def send_email(app, sign=False, encrypt=False, inline=False, attachment=None):
    app.button('New').doActionNamed('click')
    new_message = app.child('Compose Message', roleName='frame')
    new_message.textentry('To:').text = 'user@localhost,'
    new_message.childLabelled('Subject:').text = subject
    compose_document = new_message.child(
        roleName='document web')
    compose_document.click()
    compose_document.typeText('This is test message')
    if encrypt:
        new_message.menu('Options').menuItem('PGP Encrypt').doActionNamed(
            'click')
    if sign:
        new_message.menu('Options').menuItem('PGP Sign').doActionNamed('click')
    if inline:
        raise NotImplementedError(
            'toggling inline pgp not supported for evolution')
    if attachment:
        attach(app, new_message, attachment)

    new_message.button('Send').doActionNamed('click')

def receive_message(app, signed=False, encrypted=False, attachment=None):
    app.button('Send / Receive').doActionNamed('click')
    app.child(name='Inbox.*', roleName='table cell').doActionNamed('edit')
    messages = app.child('Messages', roleName='panel')
    messages.child(subject).grabFocus()
    message = app.child('Evolution Mail Display', roleName='document web')
    msg_body = message.child('.message.*', roleName='document web')\
        .children[0].text
    print('Message body: "{}"'.format(msg_body))
    assert msg_body.strip() == 'This is test message'

    # From, To, Subject, Date, Security
    gpg_info = message.findChildren(
        predicate.GenericPredicate(roleName='table cell'))[4].text

    if signed:
        assert 'signed' in gpg_info
    if encrypted:
        assert 'encrypted' in gpg_info

    if attachment:
        # check if attachment is present
        messages.parent.parent.child(os.path.basename(attachment))
        messages.parent.parent.button('Save As').doActionNamed('click')
        save_dialog = app.child('Save Attachment', roleName='frame')
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
