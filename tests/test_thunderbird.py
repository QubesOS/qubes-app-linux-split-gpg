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
from dogtail.rawinput import click, doubleClick
import subprocess
import os
import time

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


def run(cmd):
    env = os.environ.copy()
    env['GTK_MODULES'] = 'gail:atk-bridge'
    null = open(os.devnull, 'r+')
    return subprocess.Popen(
        [cmd], stdout=null, stdin=null, stderr=null, env=env)


def get_version(cmd):
    try:
        res = subprocess.check_output([cmd, '--version'])
        version = res.decode('utf-8').replace('Thunderbird ', '').split('.')[0]
    except (subprocess.SubprocessError, IndexError):
        raise Exception('Cannot determine version')
    return int(version)


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


def get_app():
    config.searchCutoffCount = 50
    tb = tree.root.application('Thunderbird|Icedove')
    config.searchCutoffCount = defaultCutoffCount
    return tb


def skip_autoconf(tb, version):
    # Icedove/Thunderbird 60+ flavor
    try:
        welcome = tb.childNamed('Mail Account Setup'
                                '|Set Up .* Existing Email .*')
        time.sleep(3)
        welcome.button('Cancel').doActionNamed('press')
    except tree.SearchError:
        pass
    if version < 78:
        # if enigmail is already installed
        try:
            tb.dialog('Enigmail Setup Wizard').button('Cancel'). \
                doActionNamed('press')
            tb.dialog('Enigmail Alert').button('Close').doActionNamed('press')
        except tree.SearchError:
            pass
    # Accept Qubes Attachment
    try:
        qubes_att = tb.child(name='Qubes Attachments added', roleName='label')
        # give it some time to settle
        time.sleep(3)
        qubes_att.parent.button('Enable').doActionNamed('press')

        qubes_att = tb.child(name='Qubes Attachments has been added.*', roleName='label')
        # give it some time to settle
        time.sleep(3)
        qubes_att.parent.button('Not now').doActionNamed('press')
    except tree.SearchError:
        pass
    config.searchCutoffCount = defaultCutoffCount


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


def add_local_account(tb, version):
    open_account_setup(tb)
    settings = tb.findChild(orPredicate(
        GenericPredicate(name='Account Settings.*', roleName='frame'),
        GenericPredicate(name='Account Settings', roleName='dialog'),
    ))
    settings.button('Account Actions').doActionNamed('press')
    settings.menuItem('Add Other Account.*').doActionNamed('click')
    wizard = tb.findChild(orPredicate(
        GenericPredicate(name='Account Wizard.*', roleName='frame'),
        GenericPredicate(name='Account Wizard', roleName='dialog'),
    ))
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
    if version >= 78:
        smtp_settings = settings.findChild(
            GenericPredicate(name='Outgoing Server (SMTP) Settings',
                             roleName='document web'))
        smtp_settings.button('Add.*').doActionNamed('press')
    else:
        settings.button('Add.*').doActionNamed('press')
    add_server = tb.findChild(orPredicate(
        GenericPredicate(name='SMTP Server.*', roleName='frame'),
        GenericPredicate(name='SMTP Server', roleName='dialog'),
    ))
    add_server.findChild(TBEntry('Description:')).text = 'localhost'
    add_server.findChild(TBEntry('Server Name:')).text = 'localhost'
    config.searchCutoffCount = 5
    if version >= 78:
        port = tb.findChild(
            GenericPredicate(name='Port:', roleName='spin button'))
    else:
        port = add_server.findChild(TBEntry('Port:'))
    port.text = '8025'
    add_server.menuItem('No authentication').doActionNamed('click')
    add_server.button('OK').doActionNamed('press')
    if version >= 78:
        file = settings.menu('File')
        file.doActionNamed('click')
        file.child('Close').doActionNamed('click')
    else:
        try:
            settings.button('OK').doActionNamed('press')
        except tree.SearchError:
            pass
    config.searchCutoffCount = defaultCutoffCount


def install_enigmail_web_search(tb, search):
    """Handle new addons manager search result which is just embedded
    addons.thunderbird.net website"""

    # search term
    search.children[0].text = 'enigmail'
    # search button
    search.children[1].doActionNamed('press')
    results = tb.child(
        name='enigmail :: Search :: Add-ons for Thunderbird',
        roleName='document web')

    # # navigation on the website is fragile and ugly, but what we can do, the
    # # old addons manager is gone
    # # find "Enigmail" link, then navigate through the table to a column to its
    # # right with "Add to Thunderbird link"
    # enigmail_link = results.findChild(GenericPredicate(name='Enigmail', roleName='link'))
    # # Enigmail (link) -> Enigmail FEATURED (heading) -> '' (section) -> '' (section)
    # # TODO: how to find next sibling? right now it relies on first result being the right one
    # time.sleep(3)
    # install_link = enigmail_link.parent.parent.parent. \
    #     children[1].child(name='Add to Thunderbird', roleName='link')

    # TODO: right now it relies on first result being the right one
    install_link = results.findChild(GenericPredicate(name='Add to Thunderbird', roleName='link'))
    install_link.doActionNamed('jump')
    config.searchCutoffCount = 20
    install_dialog = tb.findChild(orPredicate(
        GenericPredicate(name='Software Installation', roleName='frame'),
        GenericPredicate(name='Software Installation', roleName='dialog'),
        GenericPredicate(name='Add Enigmail?', roleName='label'),
    ))
    # now confirmation dialog, it needs to have focus for 3 sec until "Install"
    # button will be active
    time.sleep(3)
    if install_dialog.roleName == 'label':
        install_dialog.parent.button('Add').doActionNamed('press')
        installed = tb.child(name='Enigmail has been added.*', roleName='label')
        time.sleep(1)
        installed.parent.button('OK').doActionNamed('press')
    else:
        install_dialog.button('Install Now').doActionNamed('press')
    config.searchCutoffCount = defaultCutoffCount


def install_enigmail_builtin(tb, search):
    """Handle old, built-in search results browser"""
    # search term
    search.children[0].text = 'enigmail'
    # search button
    search.children[1].doActionNamed('press')

    addons = tb.child(name='Add-ons Manager', roleName='embedded')
    enigmail = addons.child(name='Enigmail .*More.*', roleName='list item')
    enigmail.button('Install').doActionNamed('press')
    config.searchCutoffCount = 5
    try:
        addons.button('Restart now').doActionNamed('press')
    except tree.SearchError:
        # no restart needed for this version
        addons_tab = tb.child(name='Add-ons Manager', roleName='page tab')
        addons_tab.button('').doActionNamed('press')
        return
    finally:
        config.searchCutoffCount = defaultCutoffCount

    tree.doDelay(5)
    tb = get_app()
    skip_system_integration(tb)

    tb.dialog('Enigmail Setup Wizard').button('Cancel').doActionNamed('press')
    tb.dialog('Enigmail Alert').button('Close').doActionNamed('press')
    file = tb.menu('File')
    file.doActionNamed('click')
    file.child('Close').doActionNamed('click')


def install_enigmail(tb):
    tools = tb.menu('Tools')
    tools.doActionNamed('click')
    tools.menuItem('Add-ons').doActionNamed('click')
    addons = tb.child(name='Add-ons Manager', roleName='embedded')
    # check if already installed
    addons.child(name='Extensions', roleName='list item'). \
        doActionNamed('')
    time.sleep(1)
    config.searchCutoffCount = 1
    try:
        addons_list = \
            addons.findChildren(GenericPredicate(name='', roleName='list box'),
                                recursive=False)[1]
        addons_list.childNamed('Enigmail.*')
    except tree.SearchError:
        pass
    else:
        # already installed
        return
    finally:
        config.searchCutoffCount = defaultCutoffCount
    search = addons.child(
        name='Search all add-ons|Search on addons.thunderbird.net|Find more extensions',
        roleName='section')
    if 'addons.thunderbird.net' in search.name or 'Find more' in search.name:
        install_enigmail_web_search(tb, search)
    else:
        install_enigmail_builtin(tb, search)
    file = tb.menu('File')
    file.doActionNamed('click')
    file.child('Close').doActionNamed('click')

    # in case where addons tab is still here
    try:
        addons = tb.child(name='Add-ons Manager', roleName='embedded')
        if addons:
            file = tb.menu('File')
            file.doActionNamed('click')
            file.child('Close').doActionNamed('click')
    except tree.SearchError:
        pass


def configure_enigmail_global(tb):
    # disable p≡p Junior before creating an account, see
    # https://sourceforge.net/p/enigmail/bugs/904/
    menu = tb.menu('Edit')
    menu.doActionNamed('click')
    menu.menuItem('Preferences').doActionNamed('click')
    config.searchCutoffCount = 20
    preferences = tb.findChild(orPredicate(
        GenericPredicate(name='Thunderbird Preferences.*', roleName='frame'),
        GenericPredicate(name='Thunderbird Preferences', roleName='dialog'),
    ))
    try:
        preferences.child(name='Privacy', roleName='radio button'). \
            doActionNamed('select')
    except tree.SearchError:
        preferences.child(name='Privacy', roleName='list item'). \
            doActionNamed('')
    config.searchCutoffCount = defaultCutoffCount
    preferences.child(
        name='Force using S/MIME and Enigmail',
        roleName='radio button'). \
        doActionNamed('select')
    config.searchCutoffCount = 5
    try:
        tb.child(name='Thunderbird Preferences', roleName='page tab'). \
            button('').doActionNamed('press')
    except tree.SearchError:
        preferences.button('Close').doActionNamed('press')
    config.searchCutoffCount = defaultCutoffCount

    menu = tb.menu('Enigmail.*')
    menu.doActionNamed('click')
    menu.menuItem('Preferences').doActionNamed('click')

    enigmail_prefs = tb.dialog('Enigmail Preferences')
    # wait for dialog to really initialize, otherwise it may load defaults
    # over just set values
    time.sleep(1)
    try:
        enigmail_prefs.child(name='Override with',
                             roleName='check box').doActionNamed('check')
        enigmail_prefs.child(
            name='Override with',
            roleName='section').children[0].text = \
            '/usr/bin/qubes-gpg-client-wrapper'
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
        config.searchCutoffCount = defaultCutoffCount


def configure_openpgp_global(tb):
    menu = tb.menu('Edit')
    menu.doActionNamed('click')
    menu.menuItem('Preferences').doActionNamed('click')

    preferences = tb.findChild(
        GenericPredicate(name='Preferences.*', roleName='frame'))
    config_editor = preferences.findChild(
        GenericPredicate(name='Config Editor.*', roleName='push button'))
    config_editor.doActionNamed('press')
    preferences.findChild(GenericPredicate(
        name='I accept the risk!',
        roleName='push button')).doActionNamed('press')
    about_config = preferences.findChild(
        GenericPredicate(name='about:config', roleName='embedded'))
    search = about_config.findChild(
        GenericPredicate(name='Search:', roleName='unknown'))

    search.children[0].text = 'mail.openpgp.allow_external_gnupg'
    allow_external_gnupg = preferences.findChild(GenericPredicate(
        name='mail.openpgp.allow_external_gnupg default boolean false',
        roleName='table row'))
    doubleClick(*allow_external_gnupg.position)

    search.children[0].text = 'mail.openpgp.alternative_gpg_path'
    alternative_gpg_path = preferences.findChild(GenericPredicate(
        name='mail.openpgp.alternative_gpg_path default string.*',
        roleName='table row'))
    doubleClick(*alternative_gpg_path.position)

    gpg_entry_value = tb.findChild(
        GenericPredicate(name='Enter string value', roleName='frame'))
    gpg_entry_value.findChild(GenericPredicate(
        roleName='entry')).text = '/usr/bin/qubes-gpg-client-wrapper'
    gpg_entry_value.findChild(
        GenericPredicate(name='OK', roleName='push button')).doActionNamed(
        'press')
    file = preferences.menu('File')
    file.doActionNamed('click')
    file.child('Close').doActionNamed('click')


def show_menu_bar(tb):
    config.searchCutoffCount = 20
    app = tb.findChild(
        GenericPredicate(name='Application', roleName='menu bar'))
    app.findChild(GenericPredicate(
        name='View', roleName='menu')).doActionNamed('click')
    app.findChild(GenericPredicate(
        name='Toolbars', roleName='menu')).doActionNamed('click')
    app.findChild(GenericPredicate(
        name='Menu Bar', roleName='check menu item')).doActionNamed('click')
    config.searchCutoffCount = defaultCutoffCount


def disable_html(tb, version):
    open_account_setup(tb)
    settings = tb.findChild(orPredicate(
        GenericPredicate(name='Account Settings.*', roleName='frame'),
        GenericPredicate(name='Account Settings', roleName='dialog'),
    ))
    # assume only one account...
    settings.childNamed('Composition & Addressing').doActionNamed('activate')
    config.searchCutoffCount = 5
    try:
        settings.childNamed('Compose messages in HTML format').doActionNamed(
            'uncheck')
    except tree.ActionNotSupported:
        pass
    if version >= 78:
        file = settings.menu('File')
        file.doActionNamed('click')
        file.child('Close').doActionNamed('click')
    else:
        try:
            settings.button('OK').doActionNamed('press')
        except tree.SearchError:
            pass


def configure_enigmail_account(tb):
    open_account_setup(tb)
    settings = tb.dialog('Account Settings')
    # assume only one account...
    settings.childNamed('OpenPGP Security').doActionNamed('activate')
    # enigmail will do a couple of calls to gpg, give it some time
    time.sleep(4)
    try:
        settings.childNamed('Enable OpenPGP.*').doActionNamed('check')
    except tree.ActionNotSupported:
        pass
    settings.button('OK').doActionNamed('press')


def configure_openpgp_account(tb):
    keyid = get_key_fpr()
    export_pub_key()
    open_account_setup(tb)
    settings = tb.findChild(orPredicate(
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
    key_manager = tb.findChild(
        GenericPredicate(name='OpenPGP Key Manager', roleName='frame'))
    key_manager.findChild(
        GenericPredicate(name='File', roleName='menu')).doActionNamed('click')
    key_manager.findChild(
        GenericPredicate(name='Import Public Key(s) From File',
                         roleName='menu item')).doActionNamed('click')
    file_chooser = tb.findChild(GenericPredicate(name='Import OpenPGP Key File',
                                                 roleName='file chooser'))
    click(*file_chooser.childNamed('Home').position)
    click(*file_chooser.childNamed('pub.asc').position)
    file_chooser.childNamed('Open').doActionNamed('click')
    accept_dialog = tb.findChild(
        GenericPredicate(name='.*(%s).*' % keyid)).parent
    accept_dialog.childNamed('OK').doActionNamed('press')
    tb.childNamed('Success! Keys imported.*').childNamed('OK').doActionNamed(
        'press')
    doubleClick(*key_manager.findChild(
        GenericPredicate(name='Qubes test <user@localhost>.*')).position)
    key_property = tb.findChild(
        GenericPredicate(name="Key Properties.*", roleName='frame'))
    key_property.findChild(
        GenericPredicate(name="Yes, I've verified in person.*",
                         roleName='radio button')).doActionNamed('select')
    key_property.childNamed('OK').doActionNamed('press')
    key_manager.findChild(
        GenericPredicate(name='Close', roleName='menu item')).doActionNamed(
        'click')


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
    # select_file = tb.dialog('Attach File.*')
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


def send_email(tb, version=0, sign=False, encrypt=False, inline=False,
               attachment=None):
    config.searchCutoffCount = 20
    write = tb.button('Write')
    config.searchCutoffCount = defaultCutoffCount
    write.doActionNamed('press')
    if version < 78:
        try:
            # write.menuItem('Message').doActionNamed('click')
            tb.button('Write').menuItem('Message').doActionNamed('click')
        except tree.SearchError:
            # no write what submenu
            pass
    compose = tb.child(name='Write: .*', roleName='frame')
    if version < 78:
        to_entry = compose.findChild(GenericPredicate(name='To:', roleName='autocomplete')).children[0]
    else:
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
    if version >= 78:
        security = compose.findChild(
            GenericPredicate(name='Security', roleName='push button'))
        security.doActionNamed('press')
        sign_button = security.childNamed('Digitally Sign This Message')
        encrypt_button = security.childNamed('Require Encryption')
        if sign_button.checked != sign:
            sign_button.doActionNamed('click')
        if encrypt_button.checked != encrypt:
            encrypt_button.doActionNamed('click')
    else:
        try:
            sign_button = compose.button('Sign Message')
            encrypt_button = compose.button('Encrypt Message')
        except tree.SearchError:
            # old thunderbird/enigmail
            compose.button('Enigmail Encryption Info').doActionNamed('press')
            sign_encrypt = tb.dialog('Enigmail Encryption & Signing Settings')
            encrypt_checkbox = sign_encrypt.childNamed('Encrypt Message')
            if encrypt_checkbox.checked != encrypt:
                encrypt_checkbox.doActionNamed(
                    encrypt_checkbox.actions.keys()[0])
            sign_checkbox = sign_encrypt.childNamed('Sign Message')
            if sign_checkbox.checked != sign:
                sign_checkbox.doActionNamed(sign_checkbox.actions.keys()[0])
            if inline:
                sign_encrypt.childNamed('Use Inline PGP').doActionNamed(
                    'select')
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
                enigmail_menu.menuItem('Protocol: Inline PGP').doActionNamed(
                    'click')

    if attachment:
        attach(tb, compose, attachment)
    compose.button('Send').doActionNamed('press')
    try:
        if inline and attachment:
            tb.dialog('Enigmail Prompt').button('OK').doActionNamed('press')
    except tree.SearchError:
        pass
    config.searchCutoffCount = 5
    try:
        if encrypt:
            tb.dialog('Enable Protection of Subject?'). \
                button('Protect subject').doActionNamed('press')
    except tree.SearchError:
        pass
    finally:
        config.searchCutoffCount = defaultCutoffCount


def receive_message(tb, version=0, signed=False, encrypted=False,
                    attachment=None):
    tb.child(name='user@localhost',
             roleName='table row').doActionNamed('activate')
    tb.button('Get Messages').doActionNamed('press')
    tb.menuItem('Get All New Messages').doActionNamed('click')
    tb.child(name='Inbox.*', roleName='table row').doActionNamed(
        'activate')
    config.searchCutoffCount = 5
    try:
        tb.child(name='Encrypted Message .*|.*\.\.\. .*',
                 roleName='table row').doActionNamed('activate')
    except tree.SearchError:
        pass
    finally:
        config.searchCutoffCount = defaultCutoffCount
    tb.child(name='.*{}.*'.format(subject),
             roleName='table row').doActionNamed('activate')
    # wait a little to TB decrypt/check the message
    time.sleep(2)
    # dogtail always add '$' at the end of regexp; and also "Escape all
    # parentheses, since grouping will never be needed here", so it can't be used
    # here either
    try:
        msg = tb.child(roleName='document web',
                       name=subject + '$|Encrypted Message|\.\.\.')
    except tree.SearchError:
        msg = tb.child(roleName='document frame',
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
        if version >= 78:
            if signed or encrypted:
                # 'Message Security' can be either full dialog or a popup -
                # depending on TB version
                popup = False
                tb.findChild(GenericPredicate(
                    name='View', roleName='menu')).doActionNamed('click')
                try:
                    tb.findChild(GenericPredicate(
                        name='Message Security Info',
                        roleName='menu item')).doActionNamed('click')
                    message_security = tb.child('Message Security')
                except tree.SearchError:
                    # on debian there is no menu entry, but OpenPGP button
                    # first close view menu
                    tb.findChild(GenericPredicate(
                        name='View', roleName='menu')).doActionNamed('click')
                    tb.button('OpenPGP').doActionNamed('press')
                    # 'Message Security - OpenPGP' is an internal label,
                    # nested 2 levels into the popup
                    message_security = tb.child('Message Security - OpenPGP')
                    message_security = message_security.parent.parent
                    popup = True
                if signed:
                    message_security.child('Good Digital Signature')
                if encrypted:
                    message_security.child('Message Is Encrypted')
                if not popup:
                    message_security.button('OK').doActionNamed('press')
                else:
                    message_security.parent.click()
        else:
            details = tb.button('Details')
            enigmail_status = details.parent.children[details.indexInParent - 1]
            print('Enigmail status: {}'.format(enigmail_status.text))
            if signed:
                assert 'Good signature from' in enigmail_status.text
            if encrypted:
                assert 'Decrypted message' in enigmail_status.text
    except tree.SearchError:
        if signed or encrypted:
            raise
    finally:
        config.searchCutoffCount = defaultCutoffCount

    if attachment:
        # it can be either "1 attachment:" or "2 attachments"
        attachment_label = tb.child(name='.* attachment[:s]', roleName='label')
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
        if version >= 78:
            save_as = tb.findChild(
                GenericPredicate(name='Save All Attachments',
                                 roleName='file chooser'))
            click(*save_as.childNamed('Home').position)
            click(*save_as.childNamed('Desktop').position)
            save_as.childNamed('Open').doActionNamed('click')
        else:
            subprocess.check_call(
                ['xdotool', 'search', '--name', 'Save Attachment',
                 'key', '--window', '0', '--delay', '30ms', 'ctrl+l', 'Home',
                 'type', '~/Desktop/\r'])
        # save_as = tb.dialog('Save .*Attachment.*')
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

    # tb.button('Delete').doActionNamed('press')


def quit_tb(tb):
    tb.menu('File').doActionNamed('click')
    tb.menu('File').menuItem('Quit').doActionNamed('click')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tbname', help='Thunderbird executable name',
                        default='thunderbird')
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

    # get Thunderbird version
    version = get_version(args.tbname)

    proc = run(args.tbname)
    if args.command == 'setup':
        tb = get_app()
        skip_autoconf(tb, version)
        show_menu_bar(tb)
        if version < 78:
            install_enigmail(tb)
            configure_enigmail_global(tb)
        else:
            configure_openpgp_global(tb)
        quit_tb(tb)
        subprocess.call(['pkill', 'pep-json-server'])
        proc.wait()
        proc = run(args.tbname)
        tb = get_app()
        skip_autoconf(tb, version)
        add_local_account(tb, version)
        if version < 78:
            configure_enigmail_account(tb)
        else:
            configure_openpgp_account(tb)
        disable_html(tb, version)
        quit_tb(tb)
    if args.command == 'send_receive':
        tb = get_app()
        if args.with_attachment:
            attachment = '/home/user/attachment{}.txt'.format(os.getpid())
            with open(attachment, 'w') as f:
                f.write('This is test attachment content')
        else:
            attachment = None
        send_email(tb, version=version, sign=args.signed,
                   encrypt=args.encrypted, inline=args.inline,
                   attachment=attachment)
        time.sleep(5)
        receive_message(tb, version=version, signed=args.signed,
                        encrypted=args.encrypted, attachment=attachment)
        quit_tb(tb)


if __name__ == '__main__':
    main()
