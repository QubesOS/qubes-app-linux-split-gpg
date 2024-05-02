CFLAGS+=-Wall -Wextra -Werror -O -g -fPIC -pthread
LDLIBS=-pthread -fPIC

all: gpg-client gpg-server

gpg-client: gpg-client.o multiplex.o gpg-common.o gpg-list-options.o

gpg-server: gpg-server.o multiplex.o gpg-common.o gpg-list-options.o

gpg-server.o: gpg-server.c gpg-common.h multiplex.h
gpg-client.o: gpg-client.c gpg-common.h multiplex.h

gpg-common.o: gpg-common.c gpg-common.h
gpg-list-options.o: gpg-list-options.c gpg-common.h

multiplex.o: multiplex.c multiplex.h

clean:
	rm -f ./*.o gpg-client gpg-server
