#!/usr/bin/env python3

URL="http://git.alsa-project.org/?p=alsa.git;a=blob_plain;f=hda-analyzer"
FILES=["hda_analyzer.py", "hda_guilib.py", "hda_codec.py", "hda_proc.py",
       "hda_graph.py", "hda_mixer.py"]

try:
  import gi
  gi.require_version("Gtk", "3.0")
  from gi.repository import GObject
  from gi.repository import Gtk
  from gi.repository import Pango
except:
  print("Please, install python3-gobject package")

import os
import sys
from urllib.request import urlopen

TMPDIR = ("/dev/shm"
          if os.path.exists("/dev/shm") else "/tmp") + "/hda-analyzer"
print(f"Using temporary directory: {TMPDIR}")
print("You may remove this directory when finished or if you like to")
print("download the most recent copy of hda-analyzer tool.")
if not os.path.exists(TMPDIR):
  os.mkdir(TMPDIR)
for f in FILES:
  dest = f'{TMPDIR}/{f}'
  if os.path.exists(dest):
    print(f"File cached {dest}")
    continue
  print(f"Downloading file {f}")
  with urlopen(f"{URL}/{f}") as response:
     contents = response.read()
     open(dest, "wb+").write(contents)
print("Downloaded all files")
args = ' '.join(sys.argv[1:])
if args:
  args = f" {args}"
cmd = f"python3 {TMPDIR}/{FILES[0]}{args}"
print(f"Invoking '{cmd}'")
os.system(cmd)
