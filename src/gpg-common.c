#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <assert.h>
#include <string.h>


#include "gpg-common.h"
#include "multiplex.h"

/* Add current argument (optarg) to given list
 * Check for its correctness
 */
void add_arg_to_fd_list(int *list, int *list_count)
{
	int i;
	char *endptr;
	int cur_fd, untrusted_cur_fd;

	if (*list_count >= MAX_FDS - 1) {
		fprintf(stderr, "Too many FDs specified\n");
		exit(1);
	}
	/* optarg is untrusted! */
	if (optarg[0] == 0)
		goto fail;
	untrusted_cur_fd = strtol(optarg, &endptr, 0);
	if (untrusted_cur_fd < 0)
		goto fail;
	if (endptr != NULL && endptr[0] == 0) {
		// limit fd value
		if (untrusted_cur_fd > MAX_FD_VALUE) {
			fprintf(stderr, "FD value too big (%d > %d)\n",
				untrusted_cur_fd, MAX_FD_VALUE);
			exit(1);
		}
		// check if not already in list
		for (i = 0; i < *list_count; i++) {
			if (list[i] == untrusted_cur_fd)
				break;
		}
		cur_fd = untrusted_cur_fd;
		/* FD sanitization end */
		if (i == *list_count)
			list[(*list_count)++] = cur_fd;
	} else {
fail:
		fprintf(stderr, "Invalid fd argument\n");
		exit(1);
	}
}

void handle_opt_verify(char *untrusted_sig_path, int *list, int *list_count, int is_client)
{
	int i;
	char *sig_path;
	int cur_fd, untrusted_cur_fd;
	int untrusted_sig_path_size;
	int written;

	if (*list_count >= MAX_FDS - 1) {
		fprintf(stderr, "Too many FDs used\n");
		exit(1);
	}
	if (untrusted_sig_path[0] == 0) {
		fprintf(stderr, "Invalid fd argument\n");
		exit(1);
	}
	if (sscanf(untrusted_sig_path, "/dev/fd/%d", &untrusted_cur_fd) > 0) {
		if (untrusted_cur_fd < 0) {
			fprintf(stderr, "Invalid fd argument\n");
			exit(1);
		}
		// limit fd value
		if (untrusted_cur_fd > MAX_FD_VALUE) {
			fprintf(stderr, "FD value too big (%d > %d)\n",
					untrusted_cur_fd, MAX_FD_VALUE);
			exit(1);
		}
		cur_fd = untrusted_cur_fd;
		/* FD sanitization end */
	} else {
		if (!is_client) {
			fprintf(stderr, "--verify with filename allowed on the client side\n");
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
		untrusted_sig_path_size = strlen(untrusted_sig_path)+1;
		written = snprintf(untrusted_sig_path, untrusted_sig_path_size, "/dev/fd/%d", cur_fd);
		if (written < 0 || written > untrusted_sig_path_size) {
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

int parse_options(int argc, char *untrusted_argv[], int *input_fds,
		  int *input_fds_count, int *output_fds,
		  int *output_fds_count, int is_client)
{
	int opt;
	int i, ok;
	int mode_list_keys = 0, mode_verify = 0;

	*input_fds_count = 0;
	*output_fds_count = 0;

	// Standard FDs
	input_fds[(*input_fds_count)++] = 0;	//stdin
	output_fds[(*output_fds_count)++] = 1;	//stdout
	output_fds[(*output_fds_count)++] = 2;	//stderr

	/* getopt will filter out not allowed options */
	while ((opt =
		getopt_long(argc, untrusted_argv, gpg_short_options,
			    gpg_long_options, NULL)) != -1) {
		if (opt == '?' || opt == ':') {
			/* forbidden/missing option - abort execution */
			//error message already printed by getopt
			exit(1);
		}
		i = 0;
		ok = 0;
		while (gpg_allowed_options[i]) {
			if (gpg_allowed_options[i] == opt) {
				ok = 1;
				break;
			}
			i++;
		}
		if (!ok) {
			fprintf(stderr, "Forbidden option: %s\n",
				untrusted_argv[optind - 1]);
			exit(1);
		}
		if (opt == 'k' || opt == 'K') {
			// --list-keys can have multiple key IDs as arguments
			mode_list_keys = 1;
		} else if (opt == opt_status_fd) {
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
		}

	}
	if (mode_list_keys) {
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

void move_fds(int *dest_fds, int count, int (*pipes)[2], int pipe_end)
{
	int remap_fds[MAX_FD_VALUE * 2];
	int i;

	for (i = 0; i < MAX_FD_VALUE * 2; i++)
		remap_fds[i] = -1;

	// close the other ends of pipes
	for (i = 0; i < count; i++)
		close(pipes[i][!pipe_end]);

	// move pipes to correct fds
	for (i = 0; i < count; i++) {
		// if it is currently used - move to other fd and save new position in
		// remap_fds table
		if (fcntl(dest_fds[i], F_GETFD) >= 0) {
			remap_fds[dest_fds[i]] = dup(dest_fds[i]);
			if (remap_fds[dest_fds[i]] < 0) {
				// no message - stderr closed
				exit(1);
			}
		}
		// find pipe end - possibly remapped
		while (remap_fds[pipes[i][pipe_end]] >= 0)
			pipes[i][pipe_end] = remap_fds[pipes[i][pipe_end]];
		if (dest_fds[i] != pipes[i][pipe_end]) {
			// move fd to destination position
			dup2(pipes[i][pipe_end], dest_fds[i]);
			close(pipes[i][pipe_end]);
		}
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
