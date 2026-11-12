#include "path_norm.h"

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char *
rn_status_name (rn_status status)
{
    switch (status)
    {
        case RN_OK: return "ok";
        case RN_ERR_EMPTY: return "empty-run-id";
        case RN_ERR_DOT: return "dot-segment";
        case RN_ERR_LONG: return "run-id-too-long";
        case RN_ERR_CHARSET: return "invalid-character";
        case RN_ERR_ESCAPE: return "outside-payload-root";
        default: return "bad-argument";
    }
}

rn_status
rn_run_id (const char *payload, char out[RN_MAX_RUN_ID + 1])
{
    if (!payload || !out)
        return RN_ERR_ARG;

    size_t length = strlen (payload);
    while (length > 0 && payload[length - 1] == '/')
        length--;
    if (length == 0)
        return RN_ERR_EMPTY;

    size_t start = length;
    while (start > 0 && payload[start - 1] != '/')
        start--;
    size_t count = length - start;
    if (count == 0)
        return RN_ERR_EMPTY;
    if (count > RN_MAX_RUN_ID)
        return RN_ERR_LONG;
    if ((count == 1 && payload[start] == '.') ||
        (count == 2 && payload[start] == '.' && payload[start + 1] == '.'))
        return RN_ERR_DOT;

    for (size_t index = 0; index < count; index++)
    {
        unsigned char value = (unsigned char)payload[start + index];
        if (value < 0x20 || value == '/' || value == '\\' || value == ':')
            return RN_ERR_CHARSET;
    }

    memcpy (out, payload + start, count);
    out[count] = 0;
    return RN_OK;
}

static int
is_within (const char *root, const char *candidate)
{
    size_t root_length = strlen (root);
    if (strncmp (root, candidate, root_length) != 0)
        return 0;
    if (candidate[root_length] == 0)
        return 1;
    return candidate[root_length] == '/';
}

rn_status
rn_payload_dir (const char *documents, const char *payload,
                char *out, size_t out_size)
{
    if (!documents || !payload || !out || out_size == 0)
        return RN_ERR_ARG;

    char run_id[RN_MAX_RUN_ID + 1];
    rn_status status = rn_run_id (payload, run_id);
    if (status != RN_OK)
        return status;

    if (payload[0] != '/')
    {
        char payload_root[PATH_MAX];
        int written = snprintf (payload_root, sizeof (payload_root), "%s/payload", documents);
        if (written <= 0 || (size_t)written >= sizeof (payload_root))
            return RN_ERR_LONG;

        char root_resolved[PATH_MAX];
        if (!realpath (payload_root, root_resolved))
            return RN_ERR_ESCAPE;

        char joined[PATH_MAX];
        written = snprintf (joined, sizeof (joined), "%s/%s", root_resolved, run_id);
        if (written <= 0 || (size_t)written >= sizeof (joined))
            return RN_ERR_LONG;

        char candidate[PATH_MAX];
        if (!realpath (joined, candidate))
            return RN_ERR_ESCAPE;
        if (!is_within (root_resolved, candidate))
            return RN_ERR_ESCAPE;

        if (strlen (candidate) >= out_size)
            return RN_ERR_LONG;
        strcpy (out, candidate);
        return RN_OK;
    }

    char root[PATH_MAX];
    if (!realpath (documents, root))
        return RN_ERR_ESCAPE;
    size_t root_length = strlen (root);

    char joined[PATH_MAX];
    int written = snprintf (joined, sizeof (joined), "%s/payload", root);
    if (written <= 0 || (size_t)written >= sizeof (joined))
        return RN_ERR_LONG;

    char root_resolved[PATH_MAX];
    if (!realpath (joined, root_resolved))
        return RN_ERR_ESCAPE;

    char candidate[PATH_MAX];
    if (!realpath (payload, candidate))
        return RN_ERR_ESCAPE;
    if (!is_within (root_resolved, candidate))
        return RN_ERR_ESCAPE;

    if (strlen (candidate) >= out_size)
        return RN_ERR_LONG;
    strcpy (out, candidate);
    (void)root_length;
    return RN_OK;
}

rn_status
rn_result_path (const char *documents, const char *payload,
                char *out, size_t out_size)
{
    if (!documents || !payload || !out || out_size == 0)
        return RN_ERR_ARG;

    char run_id[RN_MAX_RUN_ID + 1];
    rn_status status = rn_run_id (payload, run_id);
    if (status != RN_OK)
        return status;

    int written = snprintf (out, out_size, "%s/results/%s.json", documents, run_id);
    return (written > 0 && (size_t)written < out_size) ? RN_OK : RN_ERR_LONG;
}

rn_start_mode
rn_start_mode_select (int probe, int delivery)
{
    if (probe && delivery)
        return RN_MODE_CONFLICT;
    if (delivery)
        return RN_MODE_DELIVERY;
    if (probe)
        return RN_MODE_PROBE;
    return RN_MODE_PAYLOAD;
}

const char *
rn_start_mode_name (rn_start_mode mode)
{
    switch (mode)
    {
        case RN_MODE_PROBE: return "probe";
        case RN_MODE_DELIVERY: return "delivery";
        case RN_MODE_CONFLICT: return "conflict";
        default: return "payload";
    }
}
