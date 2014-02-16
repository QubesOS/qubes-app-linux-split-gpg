#CFLAGS=-Wall -Werror -g -DDEBUG
CFLAGS=-Wall -Wextra -Werror

all: gpg-client gpg-server pipe-cat

gpg-client: gpg-client.o multiplex.o gpg-common.o

gpg-server: gpg-server.o multiplex.o gpg-common.o

gpg-server.o: gpg-server.c gpg-common.h multiplex.h
gpg-client.o: gpg-client.c gpg-common.h multiplex.h

gpg-common.o: gpg-common.c gpg-common.h

multiplex.o: multiplex.c multiplex.h

clean:
	rm -f *.o gpg-client gpg-server pipe-cat
