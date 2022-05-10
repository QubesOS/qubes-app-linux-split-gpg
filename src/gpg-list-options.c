#include "gpg-common.h"
#include <string.h>
#include <assert.h>
#include <inttypes.h>
#include <stdlib.h>

struct lexbuf {
    uint8_t *untrusted_cursor;
};

static bool buf_consume(struct lexbuf *const buf, uint8_t const expected)
{
    bool ret = buf->untrusted_cursor[0] == expected;
    buf->untrusted_cursor += ret;
    return ret;
}

static bool is_delim(uint8_t const untrusted_c)
{
    return untrusted_c == ' ' || untrusted_c == ',';
}

/* Skip spaces and commas */
static void buf_consume_delims(struct lexbuf *const buf)
{
    while (is_delim(buf->untrusted_cursor[0]))
        buf->untrusted_cursor++;
}

static void consume_subpacket_number(struct lexbuf *const buf)
{
    char *endptr = NULL;
    long untrusted_subpacket_number = strtol((const char *)buf->untrusted_cursor, &endptr, 10);
    if (endptr == NULL)
        abort();
    if ((const uint8_t *)endptr == buf->untrusted_cursor)
        errx(1, "Invalid character in subpacket number list");
    if (untrusted_subpacket_number < 1 || untrusted_subpacket_number > 127)
        errx(1, "Subpacket number not valid (must be between 1 and 127 inclusive, got %ld)", untrusted_subpacket_number);
    buf->untrusted_cursor = (uint8_t *)endptr;
}

static void consume_subpackets_argument(struct lexbuf *const buf)
{
    if (buf_consume(buf, '"')) {
        if (!strchr((const char *)buf->untrusted_cursor, '"'))
            errx(1, "Unterminated quoted option argument");
        buf_consume_delims(buf);
        while (!buf_consume(buf, '"')) {
            consume_subpacket_number(buf);
            buf_consume_delims(buf);
        }
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

void sanitize_list_or_verify_options(const struct listopt *allowed_list_options, const char *const msg)
{
    if (!strcmp(optarg, "help"))
        return; // allow --list-options=help
    struct lexbuf buf_ = { .untrusted_cursor = (uint8_t *)optarg };
    struct lexbuf *const buf = &buf_;

    for (const char *untrusted_c = optarg; *untrusted_c; untrusted_c++) {
        /* char is signed on x86, so the first check is not redundant */
        if (*untrusted_c < 0x20 || *untrusted_c > 0x7E)
            errx(1, "Non-ASCII byte %" PRIu8 " forbidden in %s option", (uint8_t)*untrusted_c, msg);
    }

    for (;;) {
        /* Skip leading spaces and commas */
        buf_consume_delims(buf);
        if (buf->untrusted_cursor[0] == '\0')
            return; /* Nothing to do */

        /* Read the identifier */
        uint8_t *const untrusted_option = buf->untrusted_cursor;
        size_t const option_len = read_option(untrusted_option);
        if (option_len == 0)
            errx(1, "'=' not following a %s option", msg);

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

        buf->untrusted_cursor += option_len;

        while (buf_consume(buf, ' ')) {}

        if (!buf_consume(buf, '='))
            continue; /* no argument found */

        while (buf_consume(buf, ' ')) {}

        if (negated || !p->has_argument)
            errx(1, "%s option %.*s does not take an argument", msg,
                 (int)option_len, untrusted_option);

        if (buf->untrusted_cursor[0] && buf->untrusted_cursor[0] != ',')
            consume_subpackets_argument(buf);

        if (buf->untrusted_cursor[0] && !is_delim(buf->untrusted_cursor[0]))
            errx(1, "Only a space or comma can follow a %s option argument "
                    "(found %c)", msg, buf->untrusted_cursor[0]);
    }
}
