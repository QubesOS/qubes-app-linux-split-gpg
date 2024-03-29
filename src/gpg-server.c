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

const bool is_client = false;

int main(int argc, char *argv[])
{
    struct command_hdr untrusted_hdr;
    int len;
    int i;
    int remote_argc, parsed_argc;
    // use static both to reduce stack space and ensure NULL-termination
    // client can pass up to COMMAND_MAX_LEN-1 arguments, but argument 0
    // is another argument and there is also the NULL pointer that
    // terminates the argv array
    static char *(untrusted_remote_argv[COMMAND_MAX_LEN+1]);
    // same as above, but add 1 for each argument added by the server
    static char *(remote_argv[COMMAND_MAX_LEN+6]);
    int input_fds[MAX_FDS], output_fds[MAX_FDS];
    int input_fds_count, output_fds_count;

    if (argc < 3) {
        fprintf(stderr, "ERROR: Too few arguments\n");
        fprintf(stderr, "Usage: %s <gpg-path> <remote-domain>\n",
                argv[0]);
        exit(1);
    }

    len = read(0, &untrusted_hdr, sizeof(untrusted_hdr));
    if (len < 0) {
        perror("read header");
        exit(1);
    } else if (len != sizeof(untrusted_hdr)) {
        fprintf(stderr, "ERROR: Invalid header size: %d\n", len);
        exit(1);
    }
    if (untrusted_hdr.len >= COMMAND_MAX_LEN) {
        fprintf(stderr, "ERROR: Command too long\n");
        exit(1);
    }
    len = untrusted_hdr.len;
    // Check that the sender NUL-terminated their command
    if (untrusted_hdr.command[len])
        errx(1, "ERROR: command not NUL-terminated");
    // split command line into argv
    remote_argc = 0;
    untrusted_remote_argv[remote_argc++] = argv[1];
    for (i = 0; i < len; i++) {
        if (untrusted_hdr.command[i] == 0) {
            untrusted_remote_argv[remote_argc++] = &untrusted_hdr.command[i + 1];
        }
    }

    // parse arguments and do not allow any non-option argument
    if ((parsed_argc=parse_options
                (remote_argc, untrusted_remote_argv, input_fds, &input_fds_count,
                 output_fds, &output_fds_count)) < remote_argc) {
        /* allow single "-" argument */
        if (parsed_argc+1 < remote_argc ||
                strcmp(untrusted_remote_argv[parsed_argc], "-") != 0) {
            fprintf(stderr,
                    "ERROR: Non-option arguments not allowed\n");
            exit(1);
        }
    }

    memcpy(remote_argv + 6, untrusted_remote_argv + 1,
           sizeof(untrusted_remote_argv) - sizeof(untrusted_remote_argv[0]));
    /* now options are verified and we get here only when all are allowed */
    remote_argv[0] = argv[1];
    // provide a better error message than "inappropriate ioctl for device"
    remote_argv[1] = "--no-tty";
    // disable use of dirmngr, which makes no sense in a backend qube
    remote_argv[2] = "--disable-dirmngr";
    // prevent a photo viewer from being launched
    remote_argv[3] = "--photo-viewer=/bin/true";
    // force batch mode
    remote_argv[4] = "--batch";
    // ensure exit on status write error
    remote_argv[5] = "--exit-on-status-write-error";
    // Already NULL terminated as arrays are static, thus 0-initialized

    return prepare_pipes_and_run(argv[1], remote_argv, input_fds,
            input_fds_count, output_fds,
            output_fds_count);
}
