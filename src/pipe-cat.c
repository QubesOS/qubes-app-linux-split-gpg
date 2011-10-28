#include <stdlib.h>
#include <stdio.h>
#include <sys/select.h>
#include <unistd.h>
#include <fcntl.h>

#define BUF_SIZE 4096

int main(int argc, char *argv[])
{
	int len;
	fd_set read_set;
	int closed_pipe = 0;
	int closed_stdin = 0;
	int pipe_stdin, pipe_stdout;
	char buf[BUF_SIZE];

	if (argc != 3) {
		fprintf(stderr,
			"Usage: %s <pipe-to-write-stdin> <pipe-to-pass-to-stdout>\n",
			argv[0]);
		exit(1);
	}

	pipe_stdin = open(argv[1], O_WRONLY);
	if (!pipe_stdin) {
		perror("open");
		exit(1);
	}
	pipe_stdout = open(argv[2], O_RDONLY);
	if (!pipe_stdout) {
		perror("open");
		exit(1);
	}

	while (1) {
		FD_ZERO(&read_set);
		if (!closed_stdin)
			FD_SET(0, &read_set);
		if (!closed_pipe)
			FD_SET(pipe_stdout, &read_set);
		if (select(pipe_stdout + 1, &read_set, NULL, NULL, NULL) <
		    0) {
			perror("select");
			exit(1);
		}
		if (FD_ISSET(0, &read_set)) {
			len = read(0, buf, BUF_SIZE);
			if (len == 0) {
				closed_stdin = 1;
				close(pipe_stdin);
			} else {
				if (write(pipe_stdin, buf, len) < 0) {
					perror("write");
					exit(1);
				}
			}
		}
		if (FD_ISSET(pipe_stdout, &read_set)) {
			len = read(pipe_stdout, buf, BUF_SIZE);
			if (len == 0) {
				closed_pipe = 1;
				close(1);
			} else {
				if (write(1, buf, len) < 0) {
					perror("write");
					exit(1);
				}
			}
		}
		if (closed_pipe && closed_stdin)
			break;
	}

	return 0;
}
