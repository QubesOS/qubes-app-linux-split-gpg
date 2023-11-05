PANDOC=pandoc -s -f rst -t man

DOCS=$(patsubst %.rst,%.1.gz,$(wildcard *.rst))

help:
	@echo "make manpages			-- generate manpages"
	@echo "make install			-- generate manpages and copy them to /usr/share/man"

manpages: $(DOCS)

install: manpages
	install -d $(DESTDIR)/usr/share/man/man1
	install -m 0644 -D $(DOCS) $(DESTDIR)/usr/share/man/man1/

%.1: %.rst
	$(PANDOC) $< > $@

%.1.gz: %.1
	gzip -f $<

clean:
	rm -f $(DOCS)
