#include <stdlib.h>
#include <stdio.h>
#include <sys/select.h>
#include <unistd.h>
#include <fcntl.h>
#include <pthread.h>

#define BUF_SIZE 4096

struct copy_thread_args {
	int in;
	int out;
};

void *copy_thread(void *arg) {
	struct copy_thread_args *fds = arg;
	char buf[BUF_SIZE];
	int len_rd, len_wr, ret;

	while (1) {
		len_rd = read(fds->in, buf, sizeof(buf));
		if (len_rd < 0) {
			perror("read");
			exit(1);
		} else if (len_rd == 0) {
			close(fds->out);
			return NULL;
		} else {
			len_wr = 0;
			while (len_wr < len_rd) {
				ret = write(fds->out, buf+len_wr, len_rd-len_wr);
				if (ret < 0) {
					perror("write");
					exit(1);
				}
				len_wr += ret;
			}
		}
	}
	return NULL;
}

int main(int argc, char *argv[])
{
	int pipe_stdin, pipe_stdout;
	pthread_t thread_in, thread_out;
	struct copy_thread_args thread_in_args, thread_out_args;

	if (argc != 3) {
		fprintf(stderr,
			"Usage: %s <pipe-to-write-stdin> <pipe-to-pass-to-stdout>\n",
			argv[0]);
		exit(1);
	}

	pipe_stdin = open(argv[1], O_WRONLY);
	if (pipe_stdin < 0) {
		perror("open");
		exit(1);
	}
	pipe_stdout = open(argv[2], O_RDONLY);
	if (pipe_stdout < 0) {
		perror("open");
		exit(1);
	}

	thread_in_args.in = 0;
	thread_in_args.out = pipe_stdin;
	thread_out_args.in = pipe_stdout;
	thread_out_args.out = 1;
	if (pthread_create(&thread_in, NULL, copy_thread, (void*)&thread_in_args) != 0) {
		perror("pthread_create(thread_in)");
		exit(1);
	}

	if (pthread_create(&thread_out, NULL, copy_thread, (void*)&thread_out_args) != 0) {
		perror("pthread_create(thread_out)");
		exit(1);
	}

	pthread_join(thread_in, NULL);
	pthread_join(thread_out, NULL);

	return 0;
}
