#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <signal.h>
#include <sys/stat.h>
#include <time.h>
#include <fcntl.h>

#include "gpg-common.h"
#include "multiplex.h"

#define RUNDIR "/var/run/qubes-gpg-split"
#define DEFAULT_AUTOACCEPT_TIME 300

int ask_the_user(char *domain) {
	struct stat stat_buf;
	char stat_file_path[100];
	int stat_file_fd;
	char ask_cmd[512];
	time_t now;
	int autoaccept_time;

	autoaccept_time = DEFAULT_AUTOACCEPT_TIME;
	if (getenv("QUBES_GPG_AUTOACCEPT"))
		autoaccept_time = atoi(getenv("QUBES_GPG_AUTOACCEPT"));

	snprintf(stat_file_path, sizeof(stat_file_path), "%s/stat.%s", RUNDIR, domain);
	now = time(NULL);
	// if user accepts at most "autoaccept_time" seconds ago
	if (stat(stat_file_path, &stat_buf) == 0 && stat_buf.st_mtime > now-autoaccept_time )
		return 1;

	snprintf(ask_cmd, sizeof(ask_cmd), "zenity --question --text \"Do you allow"
			" VM '%s' to access your GPG keys (now and for the following %d"
				" seconds)?\"", domain, autoaccept_time);
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
			} else
				close(stat_file_fd);
			return 1;
		default:
			// "NO" or any other case
			return 0;
	}
}


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
		exit(1);
	}

	if (!ask_the_user(argv[2])) {
		fprintf(stderr, "User denied gpg access\n");
		exit(1);
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
