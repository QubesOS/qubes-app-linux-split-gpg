#### Setting for client vm ####
# VM with GPG server (default)
#export QUBES_GPG_DOMAIN="gpgvm"

# Per-VM override
if [ -s /rw/config/gpg-split-domain ]; then
    export QUBES_GPG_DOMAIN=`cat /rw/config/gpg-split-domain`
fi

#### Settings for GPG VM ####
# Remember user choice for this many seconds - default 5min (300s)
#export QUBES_GPG_AUTOACCEPT=300
