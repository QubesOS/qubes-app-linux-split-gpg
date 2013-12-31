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


#include <assert.h>
#include "multiplex.h"
#include "gpg-common.h"

#define BUF_SIZE 4096

int child_status = -1;

void sigchld_handler(int arg)
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


int process_io(int fd_input, int fd_output, int *read_fds,
	       int read_fds_len, int *write_fds, int write_fds_len)
{
	char buf[BUF_SIZE];
	int i, read_len, total_read_len;
	fd_set read_set;
	struct header hdr, untrusted_hdr;
	int closed_fds[MAX_FDS];
	int closed_fds_count = 0;
	int max_fd;
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

		FD_SET(fd_input, &read_set);
		if (fd_input > max_fd)
			max_fd = fd_input;

		if (pselect(max_fd + 1, &read_set, 0, 0, 0, &empty_set) <
		    0) {
			if (errno != EINTR) {
				perror("select");
				exit(1);
			} else {
				//EINTR
				if (closed_fds_count == read_fds_len) {
					//if child status saved - send it to the other side
					if (child_status >= 0) {
						hdr.fd_num =
						    -(child_status + 1);
						hdr.len = 0;
						if (write
						    (fd_output, &hdr,
						     sizeof(hdr)) < 0) {
							perror("write");
							return 1;
						}
					}
					return 0;
				} else
					// read remaining data and then exit
					continue;
			}
		}
		if (FD_ISSET(fd_input, &read_set)) {
			// TODO: EOF
			switch (read
				(fd_input, &untrusted_hdr, sizeof(struct header))) {
			case sizeof(struct header):
				// OK
				break;
			case 0:
				fprintf(stderr, "EOF");
				return 0;
			case -1:
				perror("read(hdr)");
				return 1;
			default:
				fprintf(stderr, "ERROR: header to small");
				exit(1);
			}
			/* header sanitization begin */
			if (untrusted_hdr.len > BUF_SIZE) {
				fprintf(stderr,
					"ERROR: Invalid block size received");
				exit(1);
			}
			if (untrusted_hdr.fd_num >= write_fds_len) {
				fprintf(stderr,
					"ERROR: invalid fd number");
				exit(1);
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
				while ((read_len = read(fd_input, buf+total_read_len,
								hdr.len-total_read_len)) > 0) {
					total_read_len += read_len;
				}
				/* we are not validating data passed to/from gpg */
				if (read_len < 0) {
					perror("read");
					return 1;
				} else if (total_read_len < hdr.len) {
					fprintf(stderr,
						"ERROR: received incomplete block "
						"(expected %d, got %d)", hdr.len, total_read_len);
					exit(1);
				}
				// writes to pipes <4kB are atomic, so no other cases
				if (write
				    (write_fds[hdr.fd_num], buf,
				     total_read_len) < 0) {
					perror("write");
					return 1;
				}
			}
		}
		for (i = 0; i < read_fds_len; i++) {
			if (FD_ISSET(read_fds[i], &read_set)) {
				// just one block
				read_len =
				    read(read_fds[i], buf, BUF_SIZE);
				/* we are not validating data passed to/from gpg */
				if (read_len < 0) {
					perror("read");
					return 1;
				}
				hdr.fd_num = i;
				hdr.len = read_len;
				// can blocks, but not a problem
				if (write(fd_output, &hdr, sizeof(hdr)) <
				    0) {
					perror("write");
					return 1;
				}
				if (read_len == 0) {
					// closed pipe
					closed_fds[read_fds[i]] = 1;
					closed_fds_count++;
					// if it was the last one - send child exit status
					if (closed_fds_count ==
					    read_fds_len
					    && child_status >= 0) {
						hdr.fd_num =
						    -(child_status + 1);
						hdr.len = 0;
						if (write
						    (fd_output, &hdr,
						     sizeof(hdr)) < 0) {
							perror("write");
							return 1;
						}
						return 0;
					}
				} else {
					// can blocks, but not a problem
					if (write(fd_output, buf, read_len)
					    < 0) {
						perror("write");
						return 1;
					}
				}
			}
		}
	}
}
