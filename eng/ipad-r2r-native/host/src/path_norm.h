#ifndef RUNECLR_PATH_NORM_H
#define RUNECLR_PATH_NORM_H

#include <stddef.h>

typedef enum {
    RN_OK = 0,
    RN_ERR_EMPTY,     /* no run id after trimming trailing slashes */
    RN_ERR_DOT,       /* "." or ".." run id */
    RN_ERR_LONG,      /* run id longer than RN_MAX_RUN_ID bytes */
    RN_ERR_CHARSET,   /* control, '/', '\\', ':' in run id */
    RN_ERR_ESCAPE,    /* absolute payload not contained in <documents>/payload */
    RN_ERR_ARG        /* bad buffer/arguments */
} rn_status;

#define RN_MAX_RUN_ID 64

const char *rn_status_name(rn_status status);

/* Last path component of payload; trailing slashes ignored. */
rn_status rn_run_id(const char *payload, char out[RN_MAX_RUN_ID + 1]);

/* Absolute or relative payload directory; absolute must resolve inside
 * <documents>/payload. Uses realpath so /var -> /private/var compares equal. */
rn_status rn_payload_dir(const char *documents, const char *payload,
                         char *out, size_t out_size);

/* <documents>/results/<run id>.json */
rn_status rn_result_path(const char *documents, const char *payload,
                         char *out, size_t out_size);

#endif
