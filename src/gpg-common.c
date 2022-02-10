/*
 * The Qubes OS Project, http://www.qubes-os.org
 *
 * Copyright (C) 2010  Rafal Wojtczuk  <rafal@invisiblethingslab.com>
 * Copyright (C) 2010  Joanna Rutkowska <joanna@invisiblethingslab.com>
 * Copyright (C) 2021  Demi Marie Obenour <demi@invisiblethingslab.com>
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 *
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <assert.h>
#include <string.h>
#include <err.h>
#include <errno.h>


#include "gpg-common.h"
#include "multiplex.h"

static int validate_fd_argument(const char *const untrusted_fd_arg) {
    if (untrusted_fd_arg == NULL || !untrusted_fd_arg[0])
        goto fail;
    const char *untrusted_p = untrusted_fd_arg;
    for (; *untrusted_p; untrusted_p++)
        if (*untrusted_p < '0' || *untrusted_p > '9')
            goto fail;
    if (untrusted_fd_arg[0] <= '0' && untrusted_fd_arg[1]) {
        fprintf(stderr, "Leading zeroes in FD argument %s not allowed\n", untrusted_fd_arg);
        exit(1);
    }
    if (untrusted_p - untrusted_fd_arg > 4)
        goto too_big;
    errno = 0;
    char *endptr = NULL;
    long const untrusted_fd = strtol(untrusted_fd_arg, &endptr, 10);
    if (untrusted_fd < 0 || untrusted_fd > 9999 || errno || !endptr || *endptr)
        abort(); // should have been caught earlier
    if (untrusted_fd >= MAX_FD_VALUE) {
too_big:
        fprintf(stderr, "FD value too big (%s > %d)\n",
                untrusted_fd_arg, MAX_FD_VALUE - 1);
        exit(1);
    }
    return (int)untrusted_fd;
fail:
    fprintf(stderr, "Invalid fd argument.  Only decimal numbers are supported.\n");
    exit(1);
}

/* Add current argument (optarg) to given list
 * Check for its correctness
 */
void add_arg_to_fd_list(int *list, int *list_count)
{
    int i, cur_fd, untrusted_cur_fd;

    if (*list_count >= MAX_FDS - 1) {
        fprintf(stderr, "Too many FDs specified\n");
        exit(1);
    }
    untrusted_cur_fd = validate_fd_argument(optarg);
    // check if not already in list
    for (i = 0; i < *list_count; i++) {
        if (list[i] == (int)untrusted_cur_fd)
            break;
    }
    cur_fd = untrusted_cur_fd;
    /* FD sanitization end */
    if (i == *list_count)
        list[(*list_count)++] = cur_fd;
}

void handle_opt_verify(char *untrusted_sig_path, int *list, int *list_count, int is_client)
{
    int i;
    char *sig_path;
    int cur_fd;
    int untrusted_sig_path_len;
    int fd_path_len;

    if (*list_count >= MAX_FDS - 1) {
        fprintf(stderr, "Too many FDs used\n");
        exit(1);
    }
    if (untrusted_sig_path[0] == 0) {
        fprintf(stderr, "Invalid fd argument\n");
        exit(1);
    }
    if (!strncmp(untrusted_sig_path, "/dev/fd/", 8)) {
        cur_fd = validate_fd_argument(untrusted_sig_path + 8);
    } else {
        if (!is_client) {
            fprintf(stderr, "--verify with filename allowed only on the client side\n");
            exit(1);
        }
        /* arguments on client side are trusted */
        sig_path = untrusted_sig_path;
        cur_fd = open(sig_path, O_RDONLY);
        if (cur_fd < 0) {
            perror("open sig");
            exit(1);
        }
        /* HACK: override original file path with FD virtual path, hope it will
         * fit; use /dev/fd instead of /proc/self/fd because is is shorter and
         * space is critical here (for thunderbird it must fit in place of "/tmp/data.sig") */
        untrusted_sig_path_len = strlen(untrusted_sig_path);
        fd_path_len = snprintf(untrusted_sig_path, untrusted_sig_path_len + 1, "/dev/fd/%d", cur_fd);
        if (fd_path_len < 0 || fd_path_len > untrusted_sig_path_len) {
            fprintf(stderr, "Failed to fit /dev/fd/%d in place of signature path\n", cur_fd);
            exit(1);
        }
        /* leak FD intentionally - process_io will read from it */
    }
    // check if not already in list
    for (i = 0; i < *list_count; i++) {
        if (list[i] == cur_fd)
            break;
    }

    if (i == *list_count)
        list[(*list_count)++] = cur_fd;
}

/* This code is taken from the GUI daemon */
static int validate_utf8_char(unsigned char *untrusted_c) {
    int tails_count = 0;
    int total_size = 0;
    /* it is safe to access byte pointed by the parameter and the next one
     * (which can be terminating NULL), but every next byte can access only if
     * neither of previous bytes was NULL
     */

    /* According to http://www.ietf.org/rfc/rfc3629.txt:
     *   UTF8-char   = UTF8-1 / UTF8-2 / UTF8-3 / UTF8-4
     *   UTF8-1      = %x00-7F
     *   UTF8-2      = %xC2-DF UTF8-tail
     *   UTF8-3      = %xE0 %xA0-BF UTF8-tail / %xE1-EC 2( UTF8-tail ) /
     *                 %xED %x80-9F UTF8-tail / %xEE-EF 2( UTF8-tail )
     *   UTF8-4      = %xF0 %x90-BF 2( UTF8-tail ) / %xF1-F3 3( UTF8-tail ) /
     *                 %xF4 %x80-8F 2( UTF8-tail )
     *   UTF8-tail   = %x80-BF
     */

    if (*untrusted_c <= 0x7F) {
        return 1;
    } else if (*untrusted_c >= 0xC2 && *untrusted_c <= 0xDF) {
        total_size = 2;
        tails_count = 1;
    } else switch (*untrusted_c) {
        case 0xE0:
            untrusted_c++;
            total_size = 3;
            if (*untrusted_c >= 0xA0 && *untrusted_c <= 0xBF)
                tails_count = 1;
            else
                return 0;
            break;
        case 0xE1: case 0xE2: case 0xE3: case 0xE4:
        case 0xE5: case 0xE6: case 0xE7: case 0xE8:
        case 0xE9: case 0xEA: case 0xEB: case 0xEC:
            /* 0xED */
        case 0xEE:
        case 0xEF:
            total_size = 3;
            tails_count = 2;
            break;
        case 0xED:
            untrusted_c++;
            total_size = 3;
            if (*untrusted_c >= 0x80 && *untrusted_c <= 0x9F)
                tails_count = 1;
            else
                return 0;
            break;
        case 0xF0:
            untrusted_c++;
            total_size = 4;
            if (*untrusted_c >= 0x90 && *untrusted_c <= 0xBF)
                tails_count = 2;
            else
                return 0;
            break;
        case 0xF1:
        case 0xF2:
        case 0xF3:
            total_size = 4;
            tails_count = 3;
            break;
        case 0xF4:
            untrusted_c++;
            if (*untrusted_c >= 0x80 && *untrusted_c <= 0x8F)
                tails_count = 2;
            else
                return 0;
            break;
        default:
            return 0;
    }

    while (tails_count-- > 0) {
        untrusted_c++;
        if (!(*untrusted_c >= 0x80 && *untrusted_c <= 0xBF))
            return 0;
    }
    return total_size;
}

/* Validate that the given string (which must be NUL-terminated) is
 * printable UTF-8 */
static void sanitize_string_from_vm(unsigned char *untrusted_s)
{
    int utf8_ret;
    for (; *untrusted_s; untrusted_s++) {
        // allow only non-control ASCII chars
        if (*untrusted_s >= 0x20 && *untrusted_s <= 0x7E)
            continue;
        if (*untrusted_s >= 0x80) {
            utf8_ret = validate_utf8_char(untrusted_s);
            if (utf8_ret > 0) {
                /* loop will do one additional increment */
                untrusted_s += utf8_ret - 1;
                continue;
            }
        }
        fputs("Command line arguments must be printable UTF-8, sorry\n", stderr);
        exit(1);
    }
}

int parse_options(int argc, char *untrusted_argv[], int *input_fds,
        int *input_fds_count, int *output_fds,
        int *output_fds_count, int is_client)
{
    int opt, command = 0;
    int longindex;
    int i, ok;
    bool userid_args = false, mode_verify = false;
    char *lastarg = NULL;
    struct listopt {
        const char *const name;
        bool const allowed;
        bool seen;
    } *p, allowed_list_options[] = {
        { "help", false, false },
        { "show-keyring", false, false },
        { "show-keyserver-urls", true, false },
        { "show-notations", true, false },
        { "show-photos", false, false },
        { "show-policy-urls", true, false },
        { "show-sig-expire", true, false },
        { "show-std-notations", true, false },
        { "show-uid-validity", true, false },
        { "show-unusable-uids", true, false },
        { "show-usage", true, false },
        { "show-user-notations", true, false },
        { NULL, false, false },
    };

    *input_fds_count = 0;
    *output_fds_count = 0;

    // Do not print error messages on the server side.  The client side should
    // have already printed an error, so the error-message generation code is
    // useless attack surface.
    if (!is_client)
        opterr = 0;

    // Standard FDs
    input_fds[(*input_fds_count)++] = 0;	//stdin
    output_fds[(*output_fds_count)++] = 1;	//stdout
    output_fds[(*output_fds_count)++] = 2;	//stderr

    for (int i = 0; i < argc; ++i) {
        if (!untrusted_argv[i])
            abort();
        sanitize_string_from_vm((unsigned char *)(untrusted_argv[i]));
    }
    if (untrusted_argv[argc])
        abort();

    /* getopt will filter out not allowed options */
    while ((void)(longindex = -1),
           (void)(lastarg = (optind <= argc ? untrusted_argv[optind] : NULL)),
           (opt = getopt_long(argc, untrusted_argv, gpg_short_options,
                              gpg_long_options, &longindex)) != -1) {
        if (opt == '?' || opt == ':') {
            /* forbidden/missing option - abort execution */
            //error message already printed by getopt
            exit(1);
        }
        i = 0;
        ok = 0;
        if (!lastarg)
            abort();
        // Number of distinct long options
        static const int opts = (int)(sizeof(gpg_long_options)/sizeof(gpg_long_options[0])) - 1;
        if (lastarg[0] == '-' && lastarg[1] == '-') {
            assert(longindex >= 0 && longindex < opts);
            const char *const optname = gpg_long_options[longindex].name;
            const size_t len = strlen(optname);
            const char *const optval = lastarg + 2;
            const char *const res = strchr(optval, '=');
            const size_t delta = res ? (size_t)(res - optval) : strlen(optval);
            if (delta > len || memcmp(optname, optval, delta)) {
                fprintf(stderr,
                        "split-gpg: internal error: option misparsed by getopt_long(3)\n");
                abort();
            }
            if (delta < len) {
                fprintf(stderr,
                        "Abbreviated option '--%.*s' must be written as '--%s'\n",
                        (int)delta, optname, optname);
                exit(1);
            }
        } else {
            assert(longindex == -1);
        }
        while (gpg_allowed_options[i]) {
            if (gpg_allowed_options[i] == opt) {
                ok = 1;
                break;
            }
            i++;
        }
        if (!ok) {
            if (longindex != -1)
                fprintf(stderr, "Forbidden option: --%s\n",
                        gpg_long_options[longindex].name);
            else
                fprintf(stderr, "Forbidden option: -%c\n", opt);
            exit(1);
        }
        i = 0;
        while (gpg_commands[i].opt) {
            if (gpg_commands[i].opt == opt) {
                if (command && userid_args != gpg_commands[i].userid_args) {
                    /* gpg gives similarly vague error message */
                    fprintf(stderr, "conflicting commands\n");
                    exit(1);
                }
                command = opt;
                userid_args = gpg_commands[i].userid_args;
                break;
            }
            i++;
        }
        if (opt == opt_status_fd) {
            add_arg_to_fd_list(output_fds, output_fds_count);
        } else if (opt == opt_logger_fd) {
            add_arg_to_fd_list(output_fds, output_fds_count);
        } else if (opt == opt_attribute_fd) {
            add_arg_to_fd_list(output_fds, output_fds_count);
#if 0
        } else if (opt == opt_passphrase_fd) {
            // this is senseless to enter password for private key in the source vm
            add_arg_to_fd_list(input_fds, input_fds_count);
#endif
        } else if (opt == opt_command_fd) {
            add_arg_to_fd_list(input_fds, input_fds_count);
        } else if (opt == opt_verify) {
            mode_verify = 1;
        } else if (opt == 'o') {
            if (strcmp(optarg, "-") != 0) {
                fprintf(stderr, "Only '-' argument supported for --output option\n");
                exit(1);
            }
        } else if (opt == opt_list_options) {
            assert(optarg);
            char const *untrusted_next_opt = optarg, *untrusted_list_opt;
            while ((untrusted_list_opt = untrusted_next_opt)) {
                size_t optlen;
                {
                    char const *const comma = strchr(untrusted_list_opt, ',');
                    if (comma) {
                        assert(comma >= untrusted_list_opt && *comma == ',');
                        untrusted_next_opt = comma + 1;
                        optlen = (size_t)(comma - untrusted_list_opt);
                    } else {
                        untrusted_next_opt = NULL;
                        optlen = strlen(untrusted_list_opt);
                    }
                    assert(optlen < COMMAND_MAX_LEN);
                }
                for (p = allowed_list_options; p->name; ++p) {
                    if (!strncmp(untrusted_list_opt, p->name, optlen) && p->name[optlen] == '\0') {
                        if (p->seen)
                            errx(1, "Duplicate list option %s", p->name);
                        if (!p->allowed)
                            errx(1, "Forbidden list option %s", p->name);
                        p->seen = true;
                        break;
                    }
                }
                if (!p->name)
                    errx(1, "Unknown list option '%.*s'", (int)optlen, untrusted_list_opt);
            }
        }

    }
    // Only allow key IDs to begin with '-' if the options list was terminated by '--',
    // or if the argument is a literal "-" (which is never considered an option)
    if (!lastarg || strcmp(lastarg, "--")) {
        for (int i = optind; i < argc; ++i) {
            const char *const untrusted_arg = untrusted_argv[i];
            if (untrusted_arg[0] == '-' && untrusted_arg[1]) {
                fprintf(stderr, "Non-option arguments must not start with '-', unless preceeded by \"--\"\n"
                                "to mark the end of options.  "
                                "As an exception, the literal string \"-\" of length 1 is allowed.\n");
                exit(1);
            }
        }
    }
    if (userid_args) {
        // all the arguments are key IDs/user IDs, so do not try to handle them
        // as input files
        optind = argc;
    }
    if (mode_verify && optind < argc) {
        handle_opt_verify(untrusted_argv[optind], input_fds, input_fds_count, is_client);
        /* the first path already processed */
        optind++;
    }

    return optind;
}

void move_fds(const int *const dest_fds, int const count, int (*const pipes)[2],
              int const pipe_end)
{
    int remap_fds[MAX_FD_VALUE * 2];
    int i;

    _Static_assert(MAX_FDS > 0 && MAX_FDS < MAX_FD_VALUE, "bad constants");
    assert(count >= 0 && count <= MAX_FDS);
    assert(pipe_end == 0 || pipe_end == 1);

    for (i = 0; i < MAX_FD_VALUE * 2; i++)
        remap_fds[i] = -1;

    // close the other ends of pipes
    for (i = 0; i < count; i++)
        close(pipes[i][!pipe_end]);

    // move pipes to correct fds
    for (i = 0; i < count; i++) {
        const int dest_fd = dest_fds[i];
#define PIPE (pipes[i][pipe_end])
        if (dest_fd < 0 || dest_fd > MAX_FD_VALUE)
            abort();
        if (PIPE < 0 || PIPE >= MAX_FD_VALUE * 2)
            _exit(1);
        // if it is currently used - move to other fd and save new position in
        // remap_fds table
        if (fcntl(dest_fd, F_GETFD) >= 0) {
            remap_fds[dest_fd] = dup(dest_fd);
            if (remap_fds[dest_fd] < 0 ||
                remap_fds[dest_fd] >= MAX_FD_VALUE * 2) {
                // no message - stderr closed
                _exit(1);
            }
        }
        // find pipe end - possibly remapped
        while (remap_fds[PIPE] >= 0) {
            PIPE = remap_fds[PIPE];
            if (PIPE >= MAX_FD_VALUE * 2)
                abort();
        }
        if (dest_fd != PIPE) {
            // move fd to destination position
            if (dup2(PIPE, dest_fd) != dest_fd)
                _exit(1);
            if (close(PIPE))
                _exit(1);
        }
#undef PIPE
    }
}

int prepare_pipes_and_run(const char *run_file, char **run_argv, int *input_fds,
        int input_fds_count, int *output_fds,
        int output_fds_count)
{
    int i;
    pid_t pid;
    int pipes_in[MAX_FDS][2];
    int pipes_out[MAX_FDS][2];
    int pipes_in_for_multiplexer[MAX_FDS];
    int pipes_out_for_multiplexer[MAX_FDS];
    sigset_t chld_set;

    sigemptyset(&chld_set);
    sigaddset(&chld_set, SIGCHLD);


    for (i = 0; i < input_fds_count; i++) {
        if (pipe(pipes_in[i]) < 0) {
            perror("pipe");
            exit(1);
        }
        // multiplexer writes to gpg through this fd
        pipes_in_for_multiplexer[i] = pipes_in[i][1];
    }
    for (i = 0; i < output_fds_count; i++) {
        if (pipe(pipes_out[i]) < 0) {
            perror("pipe");
            exit(1);
        }
        // multiplexer reads from gpg through this fd
        pipes_out_for_multiplexer[i] = pipes_out[i][0];
    }

    setup_sigchld();

    switch (pid = fork()) {
        case -1:
            perror("fork");
            exit(1);
        case 0:
            // child
            close(0);
            close(1);
            close(2);
            move_fds(input_fds, input_fds_count, pipes_in, 0);
            move_fds(output_fds, output_fds_count, pipes_out, 1);
            execv(run_file, run_argv);
            //error message already printed by getopt
            exit(1);
        default:
            // close unneded end of pipes
            for (i = 0; i < input_fds_count; i++)
                close(pipes_in[i][0]);
            for (i = 0; i < output_fds_count; i++)
                close(pipes_out[i][1]);
            sigprocmask(SIG_BLOCK, &chld_set, NULL);
            return process_io(0, 1, pipes_out_for_multiplexer,
                    output_fds_count,
                    pipes_in_for_multiplexer,
                    input_fds_count);
    }
    assert(0);
}
