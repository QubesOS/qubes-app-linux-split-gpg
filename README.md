Qubes Split GPG
===============
Split GPG implements a concept similar to having a smart card with your private 
GPG keys, except that the role of the “smart card” plays another Qubes AppVM. 
This way one, not-so-trusted domain, e.g. the one where Thunderbird is running, 
can delegate all crypto operations, such as encryption/decryption and signing to
another, more trusted, network-isolated, domain. This way the compromise of your
domain where Thunderbird or another client app is running – arguably a 
not-so-unthinkable scenario – does not allow the attacker to automatically also
steal all your keys. (We should make a rather obvious comment here that the 
so-often-used passphrases on private keys are pretty meaningless because the 
attacker can easily set up a simple backdoor which would wait until the user 
enters the passphrase and steal the key then.)

More in-depth usage information can be found 
[here](https://www.qubes-os.org/doc/split-gpg/).
