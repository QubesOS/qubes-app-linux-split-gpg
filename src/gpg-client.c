#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <string.h>
#include <err.h>

#include "gpg-common.h"
#include "multiplex.h"

#define QREXEC_CLIENT_PATH "/usr/lib/qubes/qrexec-client-vm"

const bool is_client = true;

int main(int argc, char *argv[])
{
    struct command_hdr hdr;
    int len, last_opt, i, add_dash_opt;
    int input_fds[MAX_FDS], output_fds[MAX_FDS];
    int input_fds_count, output_fds_count;
    char *qrexec_client_path = QREXEC_CLIENT_PATH, *qcp;
    char *remote_domain;
    int pipe_in[2], pipe_out[2];
    pid_t pid;

    remote_domain = getenv("QUBES_GPG_DOMAIN");
    if (!remote_domain) {
        fprintf(stderr,
                "ERROR: Destination domain not defined! Set it with QUBES_GPG_DOMAIN env variable.\n");
        exit(1);
    }
    if (!argc)
        errx(1, "ERROR: argc is 0");
    add_dash_opt = 0;
    last_opt = parse_options(argc, argv, input_fds, &input_fds_count,
            output_fds, &output_fds_count);
    if (last_opt < argc) {
        // open the first non-option argument as stdin
        int input_file;

        if (argc - last_opt > 1)
            errx(1, "Too many filename arguments");
        if (strcmp(argv[last_opt], "-") != 0) {
            /* open only when not already pointing at stdin */
            input_file = open(argv[last_opt], O_RDONLY);
            if (input_file < 0) {
                perror("open");
                exit(1);
            }
            dup2(input_file, 0);
            close(input_file);
        }
        add_dash_opt = 1;
    }
    len = 1;
    memset(hdr.command, 0, sizeof hdr.command);
    for (i = 1; i < last_opt; i++) {
        const size_t the_len = strlen(argv[i]) + 1;
        if ((size_t)COMMAND_MAX_LEN - (size_t)len < the_len) {
            fprintf(stderr, "ERROR: Command line too long\n");
            exit(1);
        } else {
            memcpy(hdr.command + len, argv[i], the_len);
            len += the_len;
        }
    }
    if (add_dash_opt) {
        if (len + 2 < COMMAND_MAX_LEN) {
            strcpy(&hdr.command[len], "-");
            len += 2;
        } else {
            fprintf(stderr, "ERROR: Command line too long\n");
            exit(1);
        }
    }

    hdr.len = len ? len - 1 : 0;

    if (pipe2(pipe_in, O_CLOEXEC) || pipe2(pipe_out, O_CLOEXEC)) {
        perror("pipe2");
        exit(1);
    }

    switch (pid = fork()) {
        case -1:
            perror("fork");
            exit(1);
        case 0:
            if (dup2(pipe_in[0], 0) != 0 || dup2(pipe_out[1], 1) != 1) {
                perror("dup2()");
                _exit(1);
            }
            qcp = getenv("QREXEC_CLIENT_PATH");
            if (qcp)
                qrexec_client_path = qcp;
            execl(qrexec_client_path, "qrexec-client-vm",
                  remote_domain, "qubes.Gpg", (char *) NULL);
            perror("exec");
            _exit(1);
    }
    // parent
    if (close(pipe_in[0]) || close(pipe_out[1])) {
        perror("close");
        exit(1);
    }
    len = write(pipe_in[1], &hdr, sizeof(hdr));
    if (len != sizeof(hdr)) {
        perror("write header");
        exit(1);
    }
#ifdef DEBUG
    fprintf(stderr, "input[0]: %d, in count: %d\n", input_fds[0],
            input_fds_count);
    fprintf(stderr, "input_pipe: %d\n", input_pipe);
#endif
    setup_sigchld();
    return process_io(pipe_out[0], pipe_in[1], input_fds,
            input_fds_count, output_fds, output_fds_count);
}
