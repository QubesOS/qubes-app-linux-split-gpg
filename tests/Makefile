#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2016 Marek Marczykowski-Górecki
#                                   <marmarek@invisiblethingslab.com>
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

PYTHON2 ?= python
PYTHON3 ?= python3

all:
	@true

install-dom0: install-dom0-py2 install-dom0-py3

install-dom0-py2:
	$(PYTHON2) setup.py install -O1 --root $(DESTDIR)

install-dom0-py3:
	$(PYTHON3) setup.py install -O1 --root $(DESTDIR)

install-vm:
	install -d $(DESTDIR)/usr/lib/qubes-gpg-split
	install test_*.py $(DESTDIR)/usr/lib/qubes-gpg-split/

install-vm-deb: install-whonix-systemd-dropins

install-whonix-systemd-dropins:
	install -d $(DESTDIR)/lib/systemd/system/bootclockrandomization.service.d/
	install whonix-clock-override.conf $(DESTDIR)/lib/systemd/system/bootclockrandomization.service.d/override.conf