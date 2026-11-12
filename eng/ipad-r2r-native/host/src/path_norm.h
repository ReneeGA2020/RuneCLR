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

/* Startup mode from the two independent flags. --probe and --delivery are
 * mutually exclusive; the caller must reject RN_MODE_CONFLICT before initializing
 * CoreCLR or running any managed code. */
typedef enum {
    RN_MODE_PAYLOAD = 0,
    RN_MODE_PROBE = 1,
    RN_MODE_DELIVERY = 2,
    RN_MODE_CONFLICT = 3
} rn_start_mode;

rn_start_mode rn_start_mode_select (int probe, int delivery);
const char *rn_start_mode_name (rn_start_mode mode);

#endif
