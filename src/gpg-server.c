#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <signal.h>

#include "gpg-common.h"
#include "multiplex.h"

int main(int argc, char *argv[], char *envp[])
{
	struct command_hdr hdr;
	int len, i;
	int remote_argc;
	char *(remote_argv[COMMAND_MAX_LEN]);	// far to big should not harm
	int input_fds[MAX_FDS], output_fds[MAX_FDS];
	int input_fds_count, output_fds_count;

	if (argc < 3) {
		fprintf(stderr, "ERROR: To few arguments\n");
		fprintf(stderr, "Usage: %s <gpg-path> <remote-domain>\n",
			argv[0]);
	}

	len = read(0, &hdr, sizeof(hdr));
	if (len < 0) {
		perror("read header");
		exit(1);
	} else if (len != sizeof(hdr)) {
		fprintf(stderr, "ERROR: Invalid header size: %d\n", len);
		exit(1);
	}
	if (hdr.len > COMMAND_MAX_LEN) {
		fprintf(stderr, "ERROR: Command to long\n");
		exit(1);
	}
	// split command line into argv
	remote_argc = 0;
	remote_argv[remote_argc++] = hdr.command;
	for (i = 0; i < hdr.len; i++) {
		if (hdr.command[i] == 0) {
			remote_argv[remote_argc++] = &hdr.command[i + 1];
		}
	}

	// parse arguments and do not allow any non-option argument
	if (parse_options
	    (remote_argc, remote_argv, input_fds, &input_fds_count,
	     output_fds, &output_fds_count) < remote_argc) {
		fprintf(stderr,
			"ERROR: Non-option arguments not allowed\n");
		exit(1);
	}
	// Add NULL terminator to argv list
	remote_argv[remote_argc] = NULL;

	return prepare_pipes_and_run(argv[1], remote_argv, input_fds,
				     input_fds_count, output_fds,
				     output_fds_count);
}
