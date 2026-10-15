#!/usr/bin/env python3
"""Install a new timing APK using the retained hash-bound asset transfer workflow."""
import argparse
import importlib.util
import inspect
from pathlib import Path

def helper(name):
    p=Path(__file__).with_name(name+'.py')
    s=importlib.util.spec_from_file_location(name.replace('-','_'),p)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
    old=helper('android-batch-kernel-install')
    source=inspect.getsource(old.main).replace("helper('android-batch-kernel-apk').adapted()[0]",
        "helper('android-batch-timing-apk').adapted()")
    source=source.replace('kernel-inputs-20261015-attempt3','timing-inputs-20261015-attempt1')
    source=source.replace('kernel-install-attempt','timing-install-attempt').replace('kernel-install-driver.py','timing-install-driver.py')
    env=dict(old.__dict__);env.update(helper=helper,__file__=__file__)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),env);env['main']()

if __name__=='__main__':main()
