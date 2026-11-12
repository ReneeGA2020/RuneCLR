#include "path_norm.h"

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int failures = 0;

static void
check (const char *name, int condition, const char *detail)
{
    printf ("%s %s%s%s\n", condition ? "PASS" : "FAIL", name,
            detail ? " detail=" : "", detail ? detail : "");
    if (!condition)
        failures++;
}

static void
check_id (const char *name, const char *payload, rn_status expect, const char *expect_id)
{
    char id[RN_MAX_RUN_ID + 1];
    rn_status status = rn_run_id (payload, id);
    int ok = status == expect && (expect != RN_OK || strcmp (id, expect_id) == 0);
    check (name, ok, ok ? NULL : rn_status_name (status));
}

static void
make_dir (const char *path)
{
    if (mkdir (path, 0700) != 0 && errno != EEXIST)
    {
        perror (path);
        exit (2);
    }
}

int
main (void)
{
    char template_path[] = "/tmp/runeclr-pathnorm-XXXXXX";
    char *scratch = mkdtemp (template_path);
    if (!scratch)
    {
        perror ("mkdtemp");
        return 2;
    }

    char documents[PATH_MAX];
    snprintf (documents, sizeof (documents), "%s/Documents", scratch);
    char payload_root[PATH_MAX];
    snprintf (payload_root, sizeof (payload_root), "%s/payload", documents);
    char run_dir[PATH_MAX];
    snprintf (run_dir, sizeof (run_dir), "%s/run1", payload_root);
    char results[PATH_MAX];
    snprintf (results, sizeof (results), "%s/results", documents);
    char outside[PATH_MAX];
    snprintf (outside, sizeof (outside), "%s/outside", scratch);
    char outside_run[PATH_MAX];
    snprintf (outside_run, sizeof (outside_run), "%s/run1", outside);

    make_dir (documents);
    make_dir (payload_root);
    make_dir (run_dir);
    make_dir (results);
    make_dir (outside);
    make_dir (outside_run);

    char link_path[PATH_MAX];
    snprintf (link_path, sizeof (link_path), "%s/link", payload_root);
    if (symlink (outside_run, link_path) != 0)
    {
        perror ("symlink");
        return 2;
    }

    check_id ("run-id-plain", "run1", RN_OK, "run1");
    check_id ("run-id-trailing-slash", "run1/", RN_OK, "run1");
    check_id ("run-id-absolute", "/var/mobile/x/Documents/payload/run1", RN_OK, "run1");
    check_id ("run-id-absolute-multi-slash", "/var/mobile/x/payload/run1///", RN_OK, "run1");
    check_id ("run-id-empty", "", RN_ERR_EMPTY, NULL);
    check_id ("run-id-only-slash", "/", RN_ERR_EMPTY, NULL);
    check_id ("run-id-dot", ".", RN_ERR_DOT, NULL);
    check_id ("run-id-dotdot", "..", RN_ERR_DOT, NULL);
    check_id ("run-id-charset-backslash", "a\\b", RN_ERR_CHARSET, NULL);
    check_id ("run-id-charset-colon", "a:b", RN_ERR_CHARSET, NULL);
    check_id ("run-id-utf8", "\xe5\x90\x8d\xe5\xad\x97-\xc3\x9f", RN_OK, "\xe5\x90\x8d\xe5\xad\x97-\xc3\x9f");
    {
        char long_id[RN_MAX_RUN_ID + 2];
        memset (long_id, 'a', sizeof (long_id) - 1);
        long_id[sizeof (long_id) - 1] = 0;
        check_id ("run-id-too-long", long_id, RN_ERR_LONG, NULL);
    }

    char out[PATH_MAX];
    char run_dir_resolved[PATH_MAX];
    int run_dir_ok = realpath (run_dir, run_dir_resolved) != NULL;
    check ("payload-relative", rn_payload_dir (documents, "run1", out, sizeof (out)) == RN_OK &&
           run_dir_ok && strcmp (out, run_dir_resolved) == 0, out);

    char absolute_payload[PATH_MAX];
    snprintf (absolute_payload, sizeof (absolute_payload), "%s/payload/run1", documents);
    rn_status absolute_status = rn_payload_dir (documents, absolute_payload, out, sizeof (out));
    char resolved_expected[PATH_MAX];
    int resolved_ok = realpath (run_dir, resolved_expected) != NULL;
    check ("payload-absolute-accepted", absolute_status == RN_OK && resolved_ok &&
           strcmp (out, resolved_expected) == 0, out);

    char absolute_trailing[PATH_MAX];
    snprintf (absolute_trailing, sizeof (absolute_trailing), "%s/payload/run1///", documents);
    check ("payload-absolute-trailing", rn_payload_dir (documents, absolute_trailing, out, sizeof (out)) == RN_OK,
           out);

    check ("payload-absolute-outside-rejected",
           rn_payload_dir (documents, outside_run, out, sizeof (out)) == RN_ERR_ESCAPE, NULL);
    check ("payload-symlink-escape-rejected",
           rn_payload_dir (documents, link_path, out, sizeof (out)) == RN_ERR_ESCAPE, NULL);

    {
        char sibling_root[PATH_MAX];
        snprintf (sibling_root, sizeof (sibling_root), "%sX/run1", payload_root);
        char sibling_parent[PATH_MAX];
        snprintf (sibling_parent, sizeof (sibling_parent), "%sX", payload_root);
        make_dir (sibling_parent);
        make_dir (sibling_root);
        check ("payload-prefix-sibling-rejected",
               rn_payload_dir (documents, sibling_root, out, sizeof (out)) == RN_ERR_ESCAPE, NULL);
    }

    check ("payload-relative-symlink-escape-rejected",
           rn_payload_dir (documents, "link", out, sizeof (out)) == RN_ERR_ESCAPE, NULL);
    check ("payload-relative-plain-accepted",
           rn_payload_dir (documents, "run1", out, sizeof (out)) == RN_OK, out);

    char result[PATH_MAX];
    char expected_result[PATH_MAX];
    snprintf (expected_result, sizeof (expected_result), "%s/results/run1.json", documents);
    check ("result-relative", rn_result_path (documents, "run1", result, sizeof (result)) == RN_OK &&
           strcmp (result, expected_result) == 0, result);
    check ("result-absolute-run-token", rn_result_path (documents, absolute_payload, result, sizeof (result)) == RN_OK &&
           strcmp (result, expected_result) == 0, result);
    check ("result-absolute-trailing", rn_result_path (documents, absolute_trailing, result, sizeof (result)) == RN_OK &&
           strcmp (result, expected_result) == 0, result);
    check ("result-absolute-outside-stays-flat",
           rn_result_path (documents, outside_run, result, sizeof (result)) == RN_OK &&
           strcmp (result, expected_result) == 0, result);
    check ("result-dot-rejected", rn_result_path (documents, "..", result, sizeof (result)) == RN_ERR_DOT, NULL);

    check ("mode-payload", rn_start_mode_select (0, 0) == RN_MODE_PAYLOAD &&
           strcmp (rn_start_mode_name (RN_MODE_PAYLOAD), "payload") == 0, NULL);
    check ("mode-probe", rn_start_mode_select (1, 0) == RN_MODE_PROBE &&
           strcmp (rn_start_mode_name (RN_MODE_PROBE), "probe") == 0, NULL);
    check ("mode-delivery", rn_start_mode_select (0, 1) == RN_MODE_DELIVERY &&
           strcmp (rn_start_mode_name (RN_MODE_DELIVERY), "delivery") == 0, NULL);
    check ("mode-conflict-is-rejected", rn_start_mode_select (1, 1) == RN_MODE_CONFLICT, NULL);
    printf ("RESULT %s failures=%d scratch=%s\n", failures == 0 ? "PASS" : "FAIL", failures, scratch);
    return failures == 0 ? 0 : 1;
}
