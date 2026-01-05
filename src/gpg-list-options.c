#include "gpg-common.h"
#include <string.h>
#include <assert.h>
#include <inttypes.h>
#include <stdlib.h>
#include <errno.h>
#include <stdio.h>

struct lexbuf {
    uint8_t *untrusted_cursor;
    uint8_t *outbuf;
    const uint8_t *const end;
};

static void buf_assert_invariants(const struct lexbuf *const buf)
{
    assert(buf != NULL);
    assert(buf->untrusted_cursor != NULL);
    assert(buf->outbuf != NULL);
    assert(buf->end != NULL);
    assert(buf->outbuf <= buf->untrusted_cursor);
    assert(buf->untrusted_cursor <= buf->end);
    assert(*buf->end == '\0');
}

static bool buf_consume(struct lexbuf *const buf, uint8_t const expected)
{
    buf_assert_invariants(buf);
    assert(expected != '\0');
    bool ret = buf->untrusted_cursor[0] == expected;
    buf->untrusted_cursor += ret;
    return ret;
}

/*
 * Add this amount of bytes to the buffer.
 * Advances the output cursor.
 * Returns pointer to the start of the data.
 * Pass NULL to shift data in-place and advance the input cursor too.
 */
static uint8_t *buf_put(struct lexbuf *buf, const uint8_t *ptr, size_t size)
{
    buf_assert_invariants(buf);
    uint8_t *const outbuf = buf->outbuf;
    if (size != 0) {
        if (ptr != NULL) {
            assert((size_t)(buf->untrusted_cursor - outbuf) >= size);
            memmove(outbuf, ptr, size);
        } else {
            assert((size_t)(buf->end - buf->untrusted_cursor) >= size);
            memmove(outbuf, buf->untrusted_cursor, size);
            buf->untrusted_cursor += size;
        }
        buf->outbuf = outbuf + size;
    }
    return outbuf;
}

static void buf_putc(struct lexbuf *buf, uint8_t c)
{
    buf_assert_invariants(buf);
    assert(buf->outbuf < buf->untrusted_cursor);
    *buf->outbuf++ = c;
}

static bool is_delim(uint8_t const untrusted_c)
{
    return untrusted_c == ' ' || untrusted_c == ',';
}

/* Skip spaces and commas */
static void buf_consume_delims(struct lexbuf *const buf)
{
    buf_assert_invariants(buf);
    while (is_delim(buf->untrusted_cursor[0]))
        buf->untrusted_cursor++;
}

static void consume_subpacket_number(struct lexbuf *const buf)
{
    buf_assert_invariants(buf);
    char *endptr = NULL;
    errno = 0;
    const uint8_t *const last = buf->untrusted_cursor;
    long untrusted_subpacket_number = strtol((const char *)last, &endptr, 10);
    if (endptr == NULL)
        abort();
    // Safety: strtol() guarantees that this is not past the NUL terminator.
    buf->untrusted_cursor = (uint8_t *)endptr;
    if ((const uint8_t *)endptr == last)
        errx(1, "Invalid character in subpacket number list");
    if (errno || untrusted_subpacket_number < 1 || untrusted_subpacket_number > 127)
        errx(1, "Subpacket number not valid (must be between 1 and 127 inclusive, got %ld)",
                untrusted_subpacket_number);
    char outbuf[4];
    int r = snprintf(outbuf, sizeof(outbuf), "%ld", untrusted_subpacket_number);
    if (r < 1 || r > 3)
        errx(1, "snprintf failed");
    switch (*endptr) {
    case '"':
    case ',':
    case ' ':
    case '\0':
        // This cannot fail an assertion because snprintf()
        // always uses the fewest bytes possible.
        buf_put(buf, (const uint8_t *)outbuf, (size_t)r);
        return;
    default:
        errx(1, "Invalid character %c following subpacket number", *endptr);
    }
}

static void consume_subpackets_argument(struct lexbuf *const buf)
{
    if (buf_consume(buf, '"')) {
        buf_putc(buf, '"');
        if (!strchr((const char *)buf->untrusted_cursor, '"'))
            errx(1, "Unterminated quoted option argument");
        buf_consume_delims(buf);
        bool seen_subpacket_number = false;
        while (!buf_consume(buf, '"')) {
            if (*buf->untrusted_cursor == '\0')
                errx(1, "Unterminated quoted option argument");
            if (seen_subpacket_number)
                buf_putc(buf, ',');
            seen_subpacket_number = true;
            consume_subpacket_number(buf);
            buf_consume_delims(buf);
        }
        buf_putc(buf, '"');
    } else {
        consume_subpacket_number(buf);
    }
}

static size_t read_option(uint8_t *untrusted_option) {
    for (size_t i = 0; ; ++i) {
        switch (untrusted_option[i]) {
        case '=':
        case ',':
        case ' ':
        case '\0':
            return i;
        case 'A'...'Z': // GnuPG is case-insensitive, but this code is case-sensitive; casefold
            untrusted_option[i] |= 0x20;
            break;
        default:
            break;
        }
    }
}

static const struct listopt *find_option(const uint8_t *const untrusted_option,
                                         size_t const len,
                                         const struct listopt *options,
                                         const char *const msg)
{
    for (; options->name; ++options) {
        if (strlen(options->name) == len &&
            memcmp(options->name, untrusted_option, len) == 0)
            break;
    }
    if (!options->name)
        errx(1, "Unknown %s option %.*s", msg, (int)len, untrusted_option);
    return options;
}

static void fixup_option_list(const struct listopt *allowed_list_options,
                              const char *const msg,
                              struct lexbuf *const buf)
{
    bool seen_option = false;
    for (;;) {
        /* Skip leading spaces and commas */
        buf_consume_delims(buf);
        if (buf->untrusted_cursor == buf->end) {
            break; /* Nothing to do.  Caller will NUL-terminate the buffer. */
        }

        if (seen_option) {
            /*
             * Add a comma to delimit options.
             * Proof that this will not assert:
             *
             * - Options must be followed by '\0', '=', ',' or ' '.
             * - If the option is followed by '\0' the loop exits above.
             * - If the option is followed by ' ' or ',', the above buf_consume_delims() call
             *   advances the cursor, unless it has already been advanced below.
             * - If the option is followed by '=', it is required to be followed by ' ' or ','
             *   after the option argument.  buf_consume_delims() will consume it.
             */
            buf_putc(buf, ',');
        }
        seen_option = true;

        /* Read the identifier */
        size_t const option_len = read_option(buf->untrusted_cursor);
        if (option_len == 0)
            errx(1, "'=' not following a %s option", msg);
        /* Slide the option back. */
        uint8_t *untrusted_option = buf_put(buf, NULL, option_len);

        bool const negated = option_len >= 3 &&
                             memcmp(untrusted_option, "no-", 3) == 0;
        const struct listopt *const p = negated ?
            find_option(untrusted_option + 3, option_len - 3,
                        allowed_list_options, msg) :
            find_option(untrusted_option, option_len,
                        allowed_list_options, msg);

        if (!(negated ? p->allowed_negated : p->allowed))
            errx(1, "Forbidden %s option %.*s", msg,
                 (int)option_len, untrusted_option);

        while (buf_consume(buf, ' ')) {}

        if (!buf_consume(buf, '='))
            continue; /* no argument found */

        while (buf_consume(buf, ' ')) {}

        if (negated || !p->has_argument)
            errx(1, "%s option %.*s does not take an argument", msg,
                 (int)option_len, untrusted_option);
        /* just consumed an '=' so this is okay */
        buf_putc(buf, '=');

        if (buf->untrusted_cursor[0] && buf->untrusted_cursor[0] != ',')
            consume_subpackets_argument(buf);

        if (buf->untrusted_cursor[0] && !is_delim(buf->untrusted_cursor[0]))
            errx(1, "Only a space or comma can follow a %s option argument "
                    "(found %c)", msg, buf->untrusted_cursor[0]);
    }
}

void sanitize_option_list(const struct listopt *allowed_list_options, const char *const msg)
{
    if (!strcmp(optarg, "help"))
        return; // allow --list-options=help

    for (const char *untrusted_c = optarg; *untrusted_c; untrusted_c++) {
        /* char is signed on x86, so the first check is not redundant */
        if (*untrusted_c < 0x20 || *untrusted_c > 0x7E)
            errx(1, "Non-ASCII byte %" PRIu8 " forbidden in %s option", (uint8_t)*untrusted_c, msg);
    }

    struct lexbuf buf = {
        .untrusted_cursor = (uint8_t *)optarg,
        .outbuf = (uint8_t *)optarg,
        .end = (const uint8_t *)optarg + strlen(optarg),
    };
    fixup_option_list(allowed_list_options, msg, &buf);
    /* NUL terminate the buffer */
    memset(buf.outbuf, 0, (size_t)(buf.end - buf.outbuf));
}
