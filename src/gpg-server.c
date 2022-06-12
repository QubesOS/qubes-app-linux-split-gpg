#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <signal.h>
#include <sys/stat.h>
#include <time.h>
#include <fcntl.h>
#include <string.h>

#include "gpg-common.h"
#include "multiplex.h"

int main(int argc, char *argv[])
{
    // make space for terminating NUL character
    char untrusted_hdr_buf[sizeof(struct command_hdr)+1];
    struct command_hdr *untrusted_hdr = (struct command_hdr*)untrusted_hdr_buf;
    int len;
    int i;
    int remote_argc, parsed_argc;
    static char *(untrusted_remote_argv[COMMAND_MAX_LEN+1]);	// far too big should not harm
    static char *(remote_argv[COMMAND_MAX_LEN+4]);	// far too big should not harm
    int input_fds[MAX_FDS], output_fds[MAX_FDS];
    int input_fds_count, output_fds_count;

    if (argc < 3) {
        fprintf(stderr, "ERROR: Too few arguments\n");
        fprintf(stderr, "Usage: %s <gpg-path> <remote-domain>\n",
                argv[0]);
        exit(1);
    }

    len = read(0, untrusted_hdr, sizeof(*untrusted_hdr));
    if (len < 0) {
        perror("read header");
        exit(1);
    } else if (len != sizeof(*untrusted_hdr)) {
        fprintf(stderr, "ERROR: Invalid header size: %d\n", len);
        exit(1);
    }
    if (untrusted_hdr->len > COMMAND_MAX_LEN) {
        fprintf(stderr, "ERROR: Command too long\n");
        exit(1);
    }
    len = untrusted_hdr->len;
    // split command line into argv
    remote_argc = 0;
    untrusted_remote_argv[remote_argc] = argv[1];
    if (len) {
        remote_argc++;
        for (i = 0; i < len-1; i++) {
            if (untrusted_hdr->command[i] == 0) {
                untrusted_remote_argv[remote_argc++] = &untrusted_hdr->command[i + 1];
            }
        }
        // don't read off the end of the buffer if sender does not NUL terminate;
        // note that we've allocated one extra byte after the struct to make
        // sure it will fit
        untrusted_hdr->command[len] = 0;
    }

    // parse arguments and do not allow any non-option argument
    if ((parsed_argc=parse_options
                (remote_argc, untrusted_remote_argv, input_fds, &input_fds_count,
                 output_fds, &output_fds_count, 0)) < remote_argc) {
        /* allow single "-" argument */
        if (parsed_argc+1 < remote_argc ||
                strcmp(untrusted_remote_argv[parsed_argc], "-") != 0) {
            fprintf(stderr,
                    "ERROR: Non-option arguments not allowed\n");
            exit(1);
        }
    }

    memcpy(remote_argv + 4, untrusted_remote_argv + 1,
           sizeof(untrusted_remote_argv) - sizeof(untrusted_remote_argv[0]));
    /* now options are verified and we get here only when all are allowed */
    remote_argv[0] = argv[1];
    // provide a better error message than "inappropriate ioctl for device"
    remote_argv[1] = "--no-tty";
    // disable use of dirmngr, which makes no sense in a backend qube
    remote_argv[2] = "--disable-dirmngr";
    // prevent a photo viewer from being launched
    remote_argv[3] = "--photo-viewer=/bin/true";
    // Already NULL terminated as arrays are static, thus 0-initialized

    return prepare_pipes_and_run(argv[1], remote_argv, input_fds,
            input_fds_count, output_fds,
            output_fds_count);
}
