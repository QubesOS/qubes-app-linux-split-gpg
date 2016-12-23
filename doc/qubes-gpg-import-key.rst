=======================
qubes-gpg-import-key(1)
=======================

NAME
====
qubes-gpg-import-key - imports a GPG key to the GPG Qube's keyring

SYNOPSIS
========
| qubes-gpg-import-key <keyfile>

DESCRIPTION
===========
qubes-gpg-import-key imports the passed key to the keyring of the GPG Qube, using
Qubes RPC. This will cause a prompt in dom0 to confirm the import before
proceeding.

AUTHORS
=======
| Marek Marczykowski <marmarek at invisiblethingslab dot com>
