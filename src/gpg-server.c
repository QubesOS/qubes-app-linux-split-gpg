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

#define RUNDIR "/var/run/qubes-gpg-split"
#define DEFAULT_AUTOACCEPT_TIME 300

int ask_the_user(const char *domain) {
    struct stat stat_buf;
    char stat_file_path[100];
    int stat_file_fd;
    char ask_cmd[512];
    time_t now;
    int autoaccept_time;
    const char *env;
    struct timespec times[2];

    autoaccept_time = DEFAULT_AUTOACCEPT_TIME;
    env = getenv("QUBES_GPG_AUTOACCEPT");
    if (env)
        autoaccept_time = atoi(env);

    snprintf(stat_file_path, sizeof(stat_file_path), "%s/stat.%s", RUNDIR, domain);
    now = time(NULL);
    // if user accepts at most "autoaccept_time" seconds ago
    if (stat(stat_file_path, &stat_buf) == 0 && stat_buf.st_mtime > now-autoaccept_time )
        return 1;

    snprintf(ask_cmd, sizeof(ask_cmd), "zenity --question --text \"Do you allow"
            " VM '%s' to access your GPG keys (now and for the following %d"
            " seconds)?\" 2>/dev/null", domain, autoaccept_time);
    switch (system(ask_cmd)) {
        case -1:
            perror("system");
            exit(1);
        case 0:
            // "YES"
            stat_file_fd = open(stat_file_path, O_WRONLY | O_CREAT, 0600);
            if (stat_file_fd < 0) {
                perror("Cannot touch stat-file");
                // continue on this error
            } else {
                times[0].tv_nsec = UTIME_OMIT;
                times[1].tv_nsec = UTIME_NOW;
                futimens(stat_file_fd, times);
                close(stat_file_fd);
            }
            return 1;
        default:
            // "NO" or any other case
            return 0;
    }
}


int main(int argc, char *argv[])
{
    // make space for terminating NUL character
    char untrusted_hdr_buf[sizeof(struct command_hdr)+1];
    struct command_hdr *untrusted_hdr = (struct command_hdr*)untrusted_hdr_buf;
    int len;
    int i;
    int remote_argc, parsed_argc;
    char *(untrusted_remote_argv[COMMAND_MAX_LEN+1]);	// far too big should not harm
    char *(remote_argv[COMMAND_MAX_LEN+1]);	// far too big should not harm
    int input_fds[MAX_FDS], output_fds[MAX_FDS];
    int input_fds_count, output_fds_count;

    if (argc < 3) {
        fprintf(stderr, "ERROR: Too few arguments\n");
        fprintf(stderr, "Usage: %s <gpg-path> <remote-domain>\n",
                argv[0]);
        exit(1);
    }

    if (!ask_the_user(argv[2])) {
        fprintf(stderr, "User denied gpg access\n");
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
    untrusted_remote_argv[remote_argc] = untrusted_hdr->command;
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
    memcpy(remote_argv, untrusted_remote_argv, sizeof(untrusted_remote_argv));
    /* now options are verified and we get here only when all are allowed */
    // Add NULL terminator to argv list
    remote_argv[remote_argc] = NULL;

    return prepare_pipes_and_run(argv[1], remote_argv, input_fds,
            input_fds_count, output_fds,
            output_fds_count);
}
