/*
 * The Qubes OS Project, http://www.qubes-os.org
 *
 * Copyright (C) 2011  Marek Marczykowski <marmarek@invisiblethingslab.com>
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

#include <sys/select.h>
#include <sys/wait.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include <pthread.h>


#include <assert.h>
#include "multiplex.h"
#include "gpg-common.h"

#define BUF_SIZE 4096

int child_status = -1;

struct thread_args{
	int multi_fd;
	int *fds;
	int fds_count;
};

void sigchld_handler(int arg __attribute__((__unused__)))
{
	int stat_loc;
	wait(&stat_loc);
	if (WIFEXITED(stat_loc))
		child_status = WEXITSTATUS(stat_loc);
}

void setup_sigchld(void)
{
	struct sigaction sa;

	sa.sa_handler = sigchld_handler;
	sa.sa_flags = 0;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGCHLD, &sa, NULL);
}

int process_in(struct thread_args *args) {
	int fd_input = args->multi_fd;
	int *write_fds = args->fds;
	int write_fds_len = args->fds_count;
	char buf[BUF_SIZE];
	struct header hdr, untrusted_hdr;
	int read_len, write_len;
	unsigned total_read_len;
	unsigned total_write_len;

	while (1) {
		total_read_len=0;
		while (total_read_len < sizeof(untrusted_hdr)) {
			read_len = read(fd_input, (&untrusted_hdr)+total_read_len,
					sizeof(struct header)-total_read_len);
			switch (read_len) {
				case 0:
					fprintf(stderr, "EOF");
					exit(EXIT_SUCCESS);
				case -1:
					perror("read(hdr)");
					exit(EXIT_FAILURE);
			}
			total_read_len += read_len;
		}
		/* header sanitization begin */
		if (untrusted_hdr.len > BUF_SIZE) {
			fprintf(stderr,
					"ERROR: Invalid block size received (%d)", untrusted_hdr.len);
			exit(EXIT_FAILURE);
		}
		if (untrusted_hdr.fd_num >= write_fds_len) {
			fprintf(stderr,
					"ERROR: invalid fd number");
			exit(EXIT_FAILURE);
		}
		hdr = untrusted_hdr;
		/* header sanitization end */
		if (hdr.fd_num < 0) {
			// received exit status from another side
			exit(-(hdr.fd_num + 1));
		}
		if (hdr.len == 0) {
			// EOF received at the other side
			close(write_fds[hdr.fd_num]);
		} else {
			/* data block can be sent in more than one chunk via vchan
			 * (because of vchan buffer size) */
			total_read_len = 0;
			while (total_read_len < hdr.len) {
				read_len = read(fd_input,
						buf+total_read_len,
						hdr.len-total_read_len);
				if (read_len < 0) {
					perror("read");
					exit(EXIT_FAILURE);
				} else if (read_len == 0) {
					fprintf(stderr,
							"ERROR: received incomplete block "
							"(expected %d, got %d)", hdr.len, total_read_len);
					exit(EXIT_FAILURE);
				}
				total_read_len += read_len;
			}
			/* we are not validating data passed to/from gpg */
			total_write_len=0;
			while (total_write_len < total_read_len) {
				write_len = write(write_fds[hdr.fd_num],
						buf+total_write_len,
						total_read_len-total_write_len);
				if (write_len < 0) {
					perror("write");

					switch (errno) {
					case -EPIPE:
					case -EBADF:
						/* broken pipes are not fatal,
						 * just discard all data */
						total_write_len = total_read_len - write_len;
						break;
					default:
						exit(EXIT_FAILURE);
					}
				}
				total_write_len += write_len;
			}
		}
	}
}

int process_out(struct thread_args *args) {
	int fd_output = args->multi_fd;
	int *read_fds = args->fds;
	int read_fds_len = args->fds_count;
	char buf[BUF_SIZE];
	int closed_fds[MAX_FDS];
	int closed_fds_count = 0;
	int max_fd;
	int i, read_len;
	fd_set read_set;
	struct header hdr;
	sigset_t empty_set;
	sigset_t chld_set;

	memset(closed_fds, 0, sizeof(closed_fds));

	sigemptyset(&empty_set);
	sigemptyset(&chld_set);
	sigaddset(&chld_set, SIGCHLD);

	while (1) {
		max_fd = 0;
		/* prepare fd_set for select */
		FD_ZERO(&read_set);
		for (i = 0; i < read_fds_len; i++) {
			if (!closed_fds[read_fds[i]]) {
				FD_SET(read_fds[i], &read_set);
				if (read_fds[i] > max_fd)
					max_fd = read_fds[i];
			}
		}
		if (pselect(max_fd + 1, &read_set, 0, 0, 0, &empty_set) <
				0) {
			if (errno != EINTR) {
				perror("select");
				exit(EXIT_FAILURE);
			} else {
				//EINTR
				if (closed_fds_count == read_fds_len) {
					//if child status saved - send it to the other side
					if (child_status >= 0) {
						hdr.fd_num = -(child_status + 1);
						hdr.len = 0;
						if (write(fd_output, &hdr, sizeof(hdr)) < 0) {
							perror("write");
							exit(EXIT_FAILURE);
						}
					}
					exit(EXIT_SUCCESS);
				} else
					// read remaining data and then exit
					continue;
			}
		}
		for (i = 0; i < read_fds_len; i++) {
			if (FD_ISSET(read_fds[i], &read_set)) {
				// just one block
				read_len = read(read_fds[i], buf, BUF_SIZE);
				/* we are not validating data passed to/from gpg */
				if (read_len < 0) {
					perror("read");
					exit(EXIT_FAILURE);
				}
				hdr.fd_num = i;
				hdr.len = read_len;
				// can blocks, but not a problem
				if (write(fd_output, &hdr, sizeof(hdr)) < 0) {
					perror("write");
					exit(EXIT_FAILURE);
				}
				if (read_len == 0) {
					// closed pipe
					closed_fds[read_fds[i]] = 1;
					closed_fds_count++;
					// if it was the last one - send child exit status
					if (closed_fds_count == read_fds_len && child_status >= 0)
					{
						hdr.fd_num = -(child_status + 1);
						hdr.len = 0;
						if (write (fd_output, &hdr, sizeof(hdr)) < 0) {
							perror("write");
							exit(EXIT_FAILURE);
						}
						exit(EXIT_SUCCESS);
					}
				} else {
					// can blocks, but not a problem
					if (write(fd_output, buf, read_len) < 0) {
						perror("write");
						exit(EXIT_FAILURE);
					}
				}
			}
		}
	}
}

int process_io(int fd_input, int fd_output, int *read_fds,
	       int read_fds_len, int *write_fds, int write_fds_len)
{
	pthread_t thread_in, thread_out;
	struct thread_args thread_in_args, thread_out_args;

	thread_in_args.multi_fd = fd_input;
	thread_in_args.fds = write_fds;
	thread_in_args.fds_count = write_fds_len;

	thread_out_args.multi_fd = fd_output;
	thread_out_args.fds = read_fds;
	thread_out_args.fds_count = read_fds_len;

	if (pthread_create(&thread_in, NULL, (void * (*)(void *))process_in, (void*)&thread_in_args) != 0) {
		perror("pthread_create(thread_in)");
		exit(EXIT_FAILURE);
	}
	if (pthread_create(&thread_out, NULL, (void * (*)(void *))process_out, (void*)&thread_out_args) != 0) {
		perror("pthread_create(thread_out)");
		exit(EXIT_FAILURE);
	}
	pthread_join(thread_out, NULL);
	pthread_join(thread_in, NULL);
	exit(EXIT_SUCCESS);
}
