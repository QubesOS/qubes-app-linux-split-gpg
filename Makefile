#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2011  Marek Marczykowski <marmarek@invisiblethingslab.com>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#

LIBDIR ?= /usr/lib

build:
	$(MAKE) -C src
	$(MAKE) -C doc manpages

install-vm-common:
	install -d $(DESTDIR)$(LIBDIR)/qubes-gpg-split
	install -t $(DESTDIR)$(LIBDIR)/qubes-gpg-split src/pipe-cat src/gpg-server
	install -D src/gpg-client $(DESTDIR)/usr/bin/qubes-gpg-client
	install -D gpg-client-wrapper $(DESTDIR)/usr/bin/qubes-gpg-client-wrapper
	install -D gpg-import-key $(DESTDIR)/usr/bin/qubes-gpg-import-key
	install -D qubes.Gpg.service $(DESTDIR)/etc/qubes-rpc/qubes.Gpg
	install -D qubes.GpgImportKey.service $(DESTDIR)/etc/qubes-rpc/qubes.GpgImportKey
	install -D qubes-gpg.sh $(DESTDIR)/etc/profile.d/qubes-gpg.sh
	install -d $(DESTDIR)/var/run/qubes-gpg-split
	install -D qubes-gpg-split.tmpfiles $(DESTDIR)/etc/tmpfiles.d/qubes-gpg-split.conf
	make -C tests install-vm
	make -C doc install

install-vm-deb: install-vm-common
	make -C tests install-vm-deb

install-vm-fedora: install-vm-common

clean:
	$(MAKE) -C src clean
	$(MAKE) -C doc clean
	rm -rf debian/changelog.*
	rm -rf pkgs
