#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <string.h>

#include "gpg-common.h"
#include "multiplex.h"

#define QREXEC_CLIENT_PATH "/usr/lib/qubes/qrexec_client_vm"
#define PIPE_CAT_PATH "/usr/lib/qubes-gpg-split/pipe-cat"

static char *client_tempdir;
static int fifo_in_created = 0, fifo_out_created = 0;

void unlink_temps(void)
{
	char tmpnam[50];
	if (fifo_in_created) {
		snprintf(tmpnam, sizeof(tmpnam), "%s/input", client_tempdir);
		unlink(tmpnam);
	}
	if (fifo_out_created) {
		snprintf(tmpnam, sizeof(tmpnam), "%s/output", client_tempdir);
		unlink(tmpnam);
	}
	rmdir(client_tempdir);
}

int main(int argc, char *argv[])
{
	struct command_hdr hdr;
	int len, last_opt, i;
	int input_fds[MAX_FDS], output_fds[MAX_FDS];
	int input_fds_count, output_fds_count;
	char tempdir[50] = "/tmp/qubes-gpg-split.XXXXXX";
	char fifo_in[50], fifo_out[50];
	int devnull;
	int input_pipe, output_pipe;
	char *qrexec_client_path = QREXEC_CLIENT_PATH, *qcp;
	char *remote_domain;
	pid_t pid;

	remote_domain = getenv("QUBES_GPG_DOMAIN");
	if (!remote_domain) {
		fprintf(stderr,
			"ERROR: Destination domain not defined! Set it with QUBES_GPG_DOMAIN env variable.\n");
		exit(1);
	}
	last_opt = parse_options(argc, argv, input_fds, &input_fds_count,
				 output_fds, &output_fds_count);
	if (last_opt < argc) {
		// open the first non-option argument as stdin
		int input_file;

		input_file = open(argv[last_opt], O_RDONLY);
		if (input_file < 0) {
			perror("open");
			exit(1);
		}
		dup2(input_file, 0);
		close(input_file);
	}
	len = 0;
	memset(hdr.command, 0, sizeof hdr.command);
	for (i = 0; i < last_opt; i++) {
		if (len + strlen(argv[i]) < COMMAND_MAX_LEN) {
			strcpy(&hdr.command[len], argv[i]);
			len += strlen(argv[i]) + 1;
		} else {
			fprintf(stderr, "ERROR: Command line too long\n");
			exit(1);
		}
	}
	hdr.len = len - 1;

	atexit(unlink_temps);
#ifndef DEBUG
	// setup fifos and run qrexec client
	if ((client_tempdir = mkdtemp(tempdir)) == NULL) {
		perror("mkdtemp");
		exit(1);
	}
#else
	client_tempdir = tempdir;
	mkdir(tempdir, 0700);
#endif
	snprintf(fifo_in, sizeof fifo_in, "%s/input", client_tempdir);
	if (mkfifo(fifo_in, 0600) < 0) {
		perror("mkfifo");
		exit(1);
	}
	fifo_in_created = 1;
	snprintf(fifo_out, sizeof fifo_out, "%s/output", client_tempdir);
	if (mkfifo(fifo_out, 0600) < 0) {
		perror("mkfifo");
		exit(1);
	}
	fifo_out_created = 1;

	switch (pid = fork()) {
	case -1:
		perror("fork");
		exit(1);
	case 0:
		devnull = open("/dev/null", O_RDONLY);
		if (devnull < 0) {
			perror("open /dev/null");
			exit(1);
		}
		dup2(devnull, 0);
		close(devnull);
		devnull = open("/dev/null", O_WRONLY);
		if (devnull < 0) {
			perror("open /dev/null");
			exit(1);
		}
		dup2(devnull, 1);
		close(devnull);

		qcp = getenv("QREXEC_CLIENT_PATH");
		if (qcp)
			qrexec_client_path = qcp;
		execl(qrexec_client_path, "qrexec_client_vm",
		      remote_domain, "qubes.Gpg", PIPE_CAT_PATH, fifo_in,
		      fifo_out, (char *) NULL);
		perror("exec");
		exit(1);
	}
	// parent

#ifdef DEBUG
	fprintf(stderr, "in: %s out: %s\n", fifo_in, fifo_out);
#endif

	input_pipe = open(fifo_in, O_RDONLY);
	if (input_pipe < 0) {
		perror("open");
		exit(1);
	}
	output_pipe = open(fifo_out, O_WRONLY);
	if (output_pipe < 0) {
		perror("open");
		exit(1);
	}

	len = write(output_pipe, &hdr, sizeof(hdr));
	if (len != sizeof(hdr)) {
		perror("write header");
		exit(1);
	}
#ifdef DEBUG
	fprintf(stderr, "input[0]: %d, in count: %d\n", input_fds[0],
		input_fds_count);
	fprintf(stderr, "input_pipe: %d\n", input_pipe);
#endif
	return process_io(input_pipe, output_pipe, input_fds,
			  input_fds_count, output_fds, output_fds_count);
}
