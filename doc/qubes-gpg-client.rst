===================
QUBES-GPG-CLIENT(1)
===================

NAME
====
qubes-gpg-client - communicates with a seperate GPG Qube to enable Qubes Split GPG

SYNOPSIS
========
| qubes-gpg-client <gpg2 options>

DESCRIPTION
===========
qubes-gpg-client functions similarly to gpg2, but performs all sensitive tasks
in a trusted Qube, defined by $QUBES_GPG_DOMAIN. Options involving network
connectivity (key servers, etc) are not supported, as the trusted GPG Qube is
intended to not have network connectivity.

OPTIONS
=======
Listed are the options that can be passed to the GPG Qube. More information can be
found about their functionality in the gpg2 manpage.

-b, --detach-sign

-a, --armor

-c, --symmetric

-d, --decrypt

-e, --encrypt

-k, --list-keys

-K, --list-secret-keys

-n, --dry-run

-o, --output

-q, --quiet

-r, --recipient

-R, --hidden-recipient

-s, --sign

-t, --textmode

-u, --local-user

-v, --verbose

--always-trust

--batch

--cert-digest-algo

--charset

--cipher-algo

--clearsign

--command-fd

--comment

--compress-algo

--digest-algo

--disable-cipher-algo

--disable-mdc

--disable-pubkey-algo

--display-charset

--emit-version

--enable-progress-filter

--encrypt-to

--export

--fingerprint

--fixed-list-mode

--fixed-list-mode

--force-mdc

--force-v3-sigs

--force-v4-certs

--gnupg

--list-config

--list-only

--list-public-keys

--list-sigs

--max-output

--no-comments

--no-encrypt-to

--no-emit-version

--no-force-v3-sigs

--no-force-v4-certs

--no-greeting

--no-secmem-warning

--no-tty

--no-verbose

--openpgp

--personal-cipher-preferences

--personal-compress-preferences

--personal-digest-preferences

--pgp2

--pgp6

--pgp7

--pgp8

--rfc1991

--rfc2440

--rfc4880

--s2k-cipher-algo

--s2k-count

--s2k-digest-algo

--s2k-mode

--status-fd

--store

--trust-model

--use-agent

--verify

--version

--with-colons

--with-fingerprint

--with-keygrip

AUTHORS
=======
| Marek Marczykowski <marmarek at invisiblethingslab dot com>
