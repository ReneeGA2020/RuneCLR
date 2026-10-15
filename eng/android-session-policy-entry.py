#!/usr/bin/env python3
"""Prepare an independent gated Android session APK driver. Never runs adb or an app."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')


GATE=r'''/* Explicit opt-in bounded gate, before CoreCLR initialization. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/prctl.h>
static int RuneCLR_EntryWait(const char* files,const char* run_id)
{
    const char* enabled=getenv("RUNECLR_SESSION_NATIVE_ENTRY_WAIT");
    if (enabled==NULL || strcmp(enabled,"1")!=0) return 0;
    if (run_id==NULL || strlen(run_id)!=32 || strspn(run_id,"0123456789abcdef")!=32) return -1;
    char release[2048];
    int count=snprintf(release,sizeof(release),"%s/session-%s.entry-release",files,run_id);
    if (count<0 || count>=(int)sizeof(release) || access(release,F_OK)==0) return -1;
    int dumpable=prctl(PR_SET_DUMPABLE,1,0,0,0);
    printf("ANDROID_ENTRY_GATE pid=%d runId=%s state=waiting dumpableResult=%d\n",getpid(),run_id,dumpable);
    fflush(stdout);
    struct timespec begin,current;
    if (clock_gettime(CLOCK_MONOTONIC,&begin)) return -1;
    while (access(release,F_OK)!=0) {
        if (clock_gettime(CLOCK_MONOTONIC,&current) || current.tv_sec-begin.tv_sec>=180) {
            printf("ANDROID_ENTRY_GATE pid=%d runId=%s state=timeout\n",getpid(),run_id);
            return -1;
        }
        usleep(20000);
    }
    printf("ANDROID_ENTRY_GATE pid=%d runId=%s state=released\n",getpid(),run_id);
    return 0;
}
'''


def gate(args):
    out=args.output.resolve();out.mkdir(exist_ok=False,parents=True)
    text=args.template.read_text()
    anchor='    LOG_INFO ("Calling coreclr_initialize");'
    declarations='#define PROPERTY_COUNT %AppContextPropertyCount%'
    if (text.count(anchor)!=1 or text.count(declarations)!=1 or 'ANDROID_SESSION_NATIVE pid=' not in text
            or 'const char* run_id = getenv("RUNECLR_SESSION_RUN_ID")' not in text):
        raise ValueError('Consume owned generated session JNI template with reviewed anchors')
    patched=text.replace(declarations,GATE+'\n'+declarations).replace(anchor,
        '    if (RuneCLR_EntryWait(g_bundle_path,run_id)!=0) return -1;\n'+anchor)
    (out/'monodroid-coreclr.c').write_text(patched)
    (out/'entry-gate.h').write_text(GATE)
    write(out/'results.json',dict(preparedOnly=True,applicationExecuted=False,template=str(args.template.resolve()),
          templateSha256=sha(args.template),generatedSha256=sha(out/'monodroid-coreclr.c'),gateSha256=sha(out/'entry-gate.h'),
          optIn='RUNECLR_SESSION_NATIVE_ENTRY_WAIT=1',timeoutSeconds=180,scope='Fresh private JNI source; no APK/runtime build'))
    print('PREPARED bounded pre-CoreCLR gate: '+str(out))


def prepare_driver(args):
    out=args.output.resolve();out.mkdir(exist_ok=False,parents=True)
    text=args.driver.read_text(encoding='utf-8-sig')
    anchor='    [IO.File]::WriteAllText($templatePath,$template,$utf8)'
    root_anchor='$repo = Split-Path $PSScriptRoot -Parent'
    if text.count(anchor)!=1 or text.count(root_anchor)!=1:
        raise ValueError('Reviewed private APK driver anchors differ')
    def quote(value):return "'"+str(value).replace("'","''")+"'"
    insertion=anchor+'\n'+(
        '    # Independent experiment: generate opt-in gate before the sole JNI native compilation.\n'
        '    $entryGate=Join-Path $evidence "entry-gate"\n'
        '    Invoke-Logged '+quote(args.python)+' @('+quote(Path(__file__).resolve())+',"gate","--template",$templatePath,"--output",$entryGate) "$evidence/entry-gate-generation.log"\n'
        '    Copy-Item -LiteralPath (Join-Path $entryGate "monodroid-coreclr.c") -Destination $templatePath\n')
    text=text.replace(root_anchor,'$repo = '+quote(args.driver.resolve().parent.parent)).replace(anchor,insertion)
    target=out/'verify-android-session-entry.ps1';target.write_text(text,encoding='utf-8-sig')
    write(out/'results.json',dict(preparedOnly=True,applicationExecuted=False,originalDriver=str(args.driver.resolve()),
          originalDriverSha256=sha(args.driver),generatedDriverSha256=sha(target),gateGeneratorSha256=sha(__file__),
          pythonExecutable=str(args.python),optIn='env:RUNECLR_SESSION_NATIVE_ENTRY_WAIT=1',
          scope='Original APK driver untouched; explicit generated gate transformation before JNI compile'))
    print('PREPARED independent gated APK driver: '+str(target))


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    g=s.add_parser('gate');g.add_argument('--template',type=Path,required=True);g.add_argument('--output',type=Path,required=True);g.set_defaults(func=gate)
    d=s.add_parser('prepare-driver');d.add_argument('--driver',type=Path,required=True);d.add_argument('--python',type=Path,required=True);d.add_argument('--output',type=Path,required=True);d.set_defaults(func=prepare_driver)
    a=p.parse_args();a.func(a)


if __name__=='__main__':main()
